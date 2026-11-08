"""Small HTTP transport; no OpenAI SDK, no implicit mutation retry."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib import request, error


class ProviderError(Exception):
    def __init__(self, message, status_code=None, outcome_unknown=False):
        super().__init__(message)
        self.status_code=status_code
        self.outcome_unknown=outcome_unknown


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):return None


class Http:
    def __init__(self, base_url, api_key, headers=None, timeout=60):
        proxy=os.environ.get('FRONTMIND_CONTENT_PROVIDER_PROXY')
        if proxy:
            provider='kimi' if urlparse(base_url).hostname=='api.moonshot.cn' else 'xty'
            base_url=proxy.rstrip('/')+'/'+provider+('/v1' if provider=='xty' else '')
            api_key='frontmind-task-proxy'
        self.base=base_url.rstrip('/')
        self.headers={'Authorization':'Bearer '+api_key,'User-Agent':'FrontMind-Workflow/16.25',**(headers or {})}
        self.timeout=timeout
        self.opener=request.build_opener(NoRedirect())

    def open(self,method,path,data=None,headers=None):
        body=data
        merged={**self.headers,**(headers or {})}
        if data is not None and not isinstance(data,bytes):
            body=json.dumps(data,ensure_ascii=False).encode('utf-8');merged['Content-Type']='application/json'
        req=request.Request(self.base+path,data=body,headers=merged,method=method)
        try:return self.opener.open(req,timeout=self.timeout)
        except error.HTTPError as exc:
            exc.close()
            raise ProviderError('HTTP_'+str(exc.code),exc.code,method!='GET' and exc.code>=500) from None
        except Exception:
            raise ProviderError('TRANSPORT_ERROR',None,method!='GET') from None

    def json(self,method,path,data=None,headers=None):
        try:
            with self.open(method,path,data,headers) as response:raw=response.read()
            return json.loads(raw.decode('utf-8')) if raw else {}
        except ProviderError:raise
        except Exception:raise ProviderError('INVALID_JSON',None,method!='GET') from None


def chat_completion(config,payload):
    """XTY Gemini only. Preserve exact payload and require a complete response upstream."""
    base=config.get('base_url','https://hk.xty.app/v1').rstrip('/').removesuffix('/chat/completions')
    http=Http(base,config['api_key'],timeout=config.get('timeout_seconds',600))
    texts=[];models=set();finish=None;usage=None;request_id=None
    with http.open('POST','/chat/completions',payload,{'Accept':'text/event-stream'}) as response:
        request_id=response.headers.get('x-request-id')
        if 'text/event-stream' not in response.headers.get('Content-Type',''):
            value=json.loads(response.read().decode('utf-8'))
            if value.get('model'):models.add(value['model'])
            usage=value.get('usage')
            for choice in value.get('choices',[]):
                texts.append(choice.get('message',{}).get('content') or '')
                finish=choice.get('finish_reason') or finish
        else:
            data=[]
            def consume(lines):
                nonlocal finish,usage
                if not lines:return
                raw='\n'.join(lines)
                if raw=='[DONE]':return
                value=json.loads(raw)
                if value.get('error'):raise ProviderError('PROVIDER_STREAM_ERROR')
                if value.get('model'):models.add(value['model'])
                if value.get('usage'):usage=value['usage']
                for choice in value.get('choices',[]):
                    text=choice.get('delta',{}).get('content')
                    if text:texts.append(text)
                    if choice.get('finish_reason'):finish=choice['finish_reason']
            for line in response:
                line=line.decode('utf-8').rstrip('\r\n')
                if line.startswith('data:'):data.append(line[5:].lstrip())
                elif not line and data:consume(data);data=[]
            if data:consume(data)
    return {'content':''.join(texts),'models':sorted(models),'finish_reason':finish,
            'usage':usage,'request_id':request_id}


def provider_config(path):
    config=json.loads(Path(path).read_text(encoding='utf-8'))
    if os.environ.get('FRONTMIND_CONTENT_PROVIDER_PROXY'):
        config['api_key']='frontmind-task-proxy'
    return config
