"""Native OpenAI Responses wire adapter for the bounded FrontMind host.

The transcript is internal bookkeeping only. Requests, original response events,
and native output items are retained separately and never labelled Chat SSE.
"""
from __future__ import annotations
import json


def native_tools(definitions):
    result = []
    for tool in definitions:
        function = tool.get('function', {})
        result.append({'type': 'function', 'name': function['name'],
            'description': function.get('description', ''),
            'parameters': function.get('parameters', {'type': 'object'}), 'strict': False})
    return result


def payload_from_messages(profile, messages, definitions):
    inputs = []
    instructions = []
    for message in messages:
        role = message.get('role')
        if role == 'system':
            instructions.append(message['content'])
        elif role == 'user':
            inputs.append({'role': 'user', 'content': message['content']})
        elif role == 'assistant':
            # Includes encrypted reasoning returned by this exact API response.
            output = message.get('response_output')
            if not isinstance(output, list):
                raise ValueError('Responses continuation requires original output items')
            inputs.extend(output)
        elif role == 'tool':
            inputs.append({'type': 'function_call_output',
                'call_id': message['tool_call_id'], 'output': message['content']})
        else:
            raise ValueError('unsupported host transcript role')
    payload = {k: v for k, v in profile.items()
        if k not in {'provider', 'api_url', 'timeout_seconds', 'wire_api'}}
    payload.update(instructions='\n\n'.join(instructions), input=inputs,
        tools=native_tools(definitions), tool_choice='auto', parallel_tool_calls=False)
    return payload


def collect_responses(events, expected_model, error_type, strict_json, on_event=None):
    """Require a real completed response; check streamed text against its output."""
    identity = model = None
    completed = None
    text_fragments, argument_fragments = {}, {}
    text_fragment_ids, text_done = {}, {}
    added, done_items = {}, {}
    def fail(code, message):
        raise error_type(code, message)
    for event in events:
        if on_event:
            on_event(event)
        if event == '[DONE]':
            # Not a Responses completion marker. Some proxies append it.
            break
        if not isinstance(event, dict) or not isinstance(event.get('type'), str):
            fail('invalid_stream_shape', 'Responses 事件缺少有效类型。')
        kind = event['type']
        if kind in {'error', 'response.failed', 'response.incomplete'} or event.get('error'):
            fail('incomplete_response', 'Responses 返回失败或未完成状态；未推进动作。')
        response = event.get('response')
        if isinstance(response, dict):
            if response.get('id'):
                if identity and identity != response['id']:
                    fail('response_identity_mismatch', 'Responses 标识在同一响应中发生变化。')
                identity = response['id']
            if response.get('model'):
                if response['model'] != expected_model:
                    fail('model_mismatch', 'API 返回模型与本版固定配置不一致，已停止。')
                model = response['model']
        if kind == 'response.output_item.added':
            index, item = event.get('output_index'), event.get('item')
            if type(index) is not int or index < 0 or not isinstance(item, dict):
                fail('invalid_stream_shape', 'Responses 输出项格式不合法。')
            if index in added:
                fail('invalid_stream_shape', 'Responses 输出项重复开始。')
            added[index] = item
        elif kind == 'response.output_item.done':
            index, item = event.get('output_index'), event.get('item')
            if type(index) is not int or index < 0 or not isinstance(item, dict):
                fail('invalid_stream_shape', 'Responses 完成项格式不合法。')
            if index in done_items:
                fail('invalid_stream_shape', 'Responses 输出项重复完成。')
            done_items[index] = item
        elif kind == 'response.output_text.delta':
            key = (event.get('output_index'), event.get('content_index'))
            if any(type(i) is not int or i < 0 for i in key) or not isinstance(event.get('delta'), str):
                fail('invalid_stream_shape', 'Responses 正文分片格式不合法。')
            if key in text_done:
                fail('stream_result_mismatch', 'Responses 正文已完成后又收到分片。')
            text_fragments.setdefault(key, []).append(event['delta'])
            text_fragment_ids.setdefault(key, []).append(event.get('item_id'))
        elif kind == 'response.output_text.done':
            key = (event.get('output_index'), event.get('content_index'))
            if any(type(i) is not int or i < 0 for i in key) or not isinstance(event.get('text'), str):
                fail('invalid_stream_shape', 'Responses 正文完成事件格式不合法。')
            if key in text_done:
                fail('stream_result_mismatch', 'Responses 正文重复完成。')
            text_done[key] = event
        elif kind == 'response.function_call_arguments.delta':
            index = event.get('output_index')
            if type(index) is not int or not isinstance(event.get('delta'), str):
                fail('invalid_tool_fragment', 'Responses 工具参数分片格式不合法。')
            argument_fragments.setdefault(index, []).append(event['delta'])
        elif kind == 'response.completed':
            if not isinstance(response, dict) or response.get('status') != 'completed':
                fail('incomplete_response', 'Responses 未明确完成。')
            completed = response
            break
    if completed is None:
        fail('incomplete_stream', 'Responses 流缺少 response.completed，不把部分响应视为完成。')
    if model is None or identity is None:
        fail('missing_model_identity', 'Responses 未返回实际模型或响应标识。')
    output = completed.get('output')
    if not isinstance(output, list):
        fail('invalid_stream_shape', 'Responses output 不是数组。')
    def verified_omitted_message_id(index, item):
        # Narrow gateway compatibility: a completed assistant text message may
        # omit its item ID, while added/delta/text.done unambiguously bind every
        # character to one ID at this exact position. Do not add that ID to the
        # raw final output, and never apply this exception to tools/reasoning.
        origin = added.get(index, {})
        known_id = origin.get('id')
        if ('id' in item or item.get('type') != 'message' or item.get('role') != 'assistant'
                or item.get('status') != 'completed'
                or origin.get('type') != 'message' or origin.get('role') != 'assistant'
                or not isinstance(known_id, str) or not known_id
                or completed.get('id') != identity or completed.get('model') != model
                or any(row.get('type') == 'function_call' for row in output if isinstance(row, dict))
                or any(i != index and row.get('id') == known_id for i, row in added.items())):
            return False
        content = item.get('content')
        if not isinstance(content, list) or not content:
            return False
        for content_index, part in enumerate(content):
            key = (index, content_index)
            done = text_done.get(key, {})
            if (not isinstance(part, dict) or part.get('type') != 'output_text'
                    or not isinstance(part.get('text'), str) or key not in text_fragments
                    or not text_fragment_ids.get(key)
                    or any(value != known_id for value in text_fragment_ids[key])
                    or done.get('item_id') != known_id
                    or ''.join(text_fragments[key]) != part['text'] or done.get('text') != part['text']):
                return False
        if index in done_items:
            done = done_items[index]
            if (done.get('id') != known_id
                    or {k: v for k, v in done.items() if k != 'id'} != item):
                return False
        return True

    text, summaries, calls, call_ids = [], [], [], set()
    protocol_observations = []
    for index, item in enumerate(output):
        if not isinstance(item, dict):
            fail('invalid_stream_shape', 'Responses 输出项不是对象。')
        omitted_message_id = False
        if ((index in added and added[index].get('id') != item.get('id'))
                or (item.get('type') == 'message' and 'id' not in item)):
            omitted_message_id = verified_omitted_message_id(index, item)
            if not omitted_message_id:
                fail('response_identity_mismatch', 'Responses 输出项标识不一致。')
            protocol_observations.append({'kind': 'completed_message_id_omitted',
                'output_index': index, 'matched_added_item_id': added[index]['id'],
                'verification': 'same_position_role_type_and_exact_delta_done_final_text'})
        if index in done_items and done_items[index] != item and not omitted_message_id:
            done = done_items[index]
            # Encrypted reasoning is an opaque continuation token. The gateway
            # may re-encrypt it at response completion; compare all semantic
            # fields and retain the final token without trying to decode it.
            opaque_only = (done.get('type') == item.get('type') == 'reasoning'
                and all(isinstance(value.get('encrypted_content'), str)
                        and value['encrypted_content'] for value in (done, item))
                and {k: v for k, v in done.items() if k != 'encrypted_content'}
                    == {k: v for k, v in item.items() if k != 'encrypted_content'})
            if not opaque_only:
                fail('stream_result_mismatch', 'Responses 完成项与最终结果不一致。')
        kind = item.get('type')
        if kind == 'function_call':
            arguments, name, call_id = item.get('arguments'), item.get('name'), item.get('call_id')
            if not all(isinstance(v, str) and v for v in (arguments, name, call_id)) or call_id in call_ids:
                fail('invalid_tool_arguments', 'Responses 工具调用缺少完整标识、名称或参数。')
            if item.get('status') not in (None, 'completed'):
                fail('incomplete_tool_calls', 'Responses 工具调用尚未完成。')
            if index in argument_fragments and ''.join(argument_fragments[index]) != arguments:
                fail('stream_result_mismatch', 'Responses 工具参数分片与最终参数不一致。')
            try:
                parsed = strict_json(arguments)
            except (ValueError, TypeError):
                fail('invalid_tool_arguments', 'Responses 工具参数 JSON 不完整。')
            if not isinstance(parsed, dict):
                fail('invalid_tool_arguments', 'Responses 工具参数必须是对象。')
            call_ids.add(call_id)
            calls.append({'id': call_id, 'type': 'function',
                'function': {'name': name, 'arguments': arguments}})
        elif kind == 'message':
            if item.get('role') != 'assistant' or item.get('status') not in (None, 'completed'):
                fail('invalid_stream_shape', 'Responses 消息角色或状态不合法。')
            for content_index, part in enumerate(item.get('content', [])):
                if part.get('type') == 'refusal':
                    fail('model_refusal', '宿主未能完成当前动作。')
                if part.get('type') != 'output_text' or not isinstance(part.get('text'), str):
                    fail('invalid_stream_shape', 'Responses 返回了非文本业务内容。')
                key = (index, content_index)
                if key in text_fragments and ''.join(text_fragments[key]) != part['text']:
                    fail('stream_result_mismatch', 'Responses 正文分片与最终正文不一致。')
                if key in text_done and text_done[key]['text'] != part['text']:
                    fail('stream_result_mismatch', 'Responses 完成正文与最终正文不一致。')
                text.append(part['text'])
        elif kind == 'reasoning':
            summaries.extend(part.get('text', '') for part in item.get('summary', []) if isinstance(part, dict))
        else:
            fail('unexpected_host_output', '宿主返回未授权的 Responses 输出类型。')
    if any(i >= len(output) for i in set(added) | set(done_items) | set(argument_fragments)):
        fail('stream_result_mismatch', 'Responses 分片没有对应最终输出项。')
    for key in set(text_fragments) | set(text_done):
        i, j = key
        if i >= len(output) or output[i].get('type') != 'message' or j >= len(output[i].get('content', [])):
            fail('stream_result_mismatch', 'Responses 正文分片没有对应最终正文。')
    return {'id': identity, 'model': model, 'content': ''.join(text),
        'reasoning_content': ''.join(summaries), 'tool_calls': calls,
        'finish_reason': 'tool_calls' if calls else 'stop',
        'usage': completed.get('usage') or {}, 'complete': True,
        'wire_api': 'responses', 'response_status': 'completed',
        'response_output': output, **({'protocol_observations': protocol_observations} if protocol_observations else {})}
