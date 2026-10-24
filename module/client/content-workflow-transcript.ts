import {
  CONTENT_PRODUCTION_RUNNER_STATUSES,
  contentProductionStagePosition,
} from "../contracts/content-production";
import type {ContentMessage} from "./host";

type WorkflowMessage = ContentMessage & {contentWorkflowPosition?:number};
const legacyPositions = [1,5,8,13,15,18] as const;

/** 只识别工作流原生文件名，不读取或推断聊天正文。 */
function artifactPosition(filename:string):number|null {
  const name = filename.replace(/\\/gu,"/").split("/").at(-1) ?? filename;
  // 确认稿使用原生状态与修订号，避免把普通客户文件名当作状态。
  if (/\.(?:md|html?)$/iu.test(name)) {
    for (const status of CONTENT_PRODUCTION_RUNNER_STATUSES) {
      if (new RegExp(`(?:^|[_-])${status}(?:[._-]r\\d+)\\.(?:md|html?)$`,"iu").test(name))
        return contentProductionStagePosition(null,status);
    }
  }
  // 资料包在 P0 交付时会再次导出，应优先识别带 P0 的版本。
  if (/(?:reference[_ -]pack[_ -]p0|品牌资料包[_ -]p0)/iu.test(name)) return 12;
  if (/(?:^|[_ -])p0(?:[_ -]?写作蓝图|[_ -]?写作方案|[_ -]blueprint)/iu.test(name)) return 10;
  if (/(?:^|[_ -])p0(?:[_ -]?正文|[_ -]?(?:候选)?标题|[_ -]?5加5标题|[_ -](?:article|draft|title[_ -]map))|(?:^|[_ -])p0\.(?:md|html?|docx)$/iu.test(name)) return 12;
  if (/问题\d*[_ -]?(?:写作蓝图|写作方案)|(?:^|[_ -])(?:article|question)[_ -]blueprint/iu.test(name)) return 18;
  if (/问题\d*[_ -]?(?:正文|候选标题|标题)|(?:^|[_ -])article(?:[_ -](?:draft|title[_ -]map))?\.(?:md|html?|docx)$/iu.test(name)) return 20;
  if (/问题\d*[_ -]?(?:参考文章与文风|参考例文与文风|文风)|(?:^|[_ -])(?:article[_ -]pool|example[_ -]confirmation)/iu.test(name)) return 16;
  if (/问题\d*[_ -]?(?:文章类型|类型确认)|(?:^|[_ -])pattern[_ -]confirmation/iu.test(name)) return 15;
  if (/问题\d*[_ -]?(?:应答要求|应答简报)|(?:^|[_ -])response[_ -]brief/iu.test(name)) return 13;
  if (/问题\d*[_ -]?定位确认稿|(?:^|[_ -])question[_ -]positioning/iu.test(name)) return 17;
  if (/核心定位确认稿/iu.test(name)) return 5;
  if (/核心定位与竞品比较|(?:^|[_ -])reference[_ -]pack(?:[_ .-]|$)|品牌资料包(?:[_ .-]|$)/iu.test(name)) return 7;
  if (/企业资料与比较范围(?:预览|确认稿)?/iu.test(name)) return 1;
  return null;
}

/** 每个原生阶段保留第一次明确出现的消息，供动态任务泳道定位。 */
export function contentWorkflowTranscriptAnchors(messages:readonly WorkflowMessage[]):Map<number,string> {
  const anchors = new Map<number,string>();
  let precedingUser:WorkflowMessage|undefined;
  for (let index=0;index<messages.length;index++) {
    const message = messages[index];
    if(message.role==="user")precedingUser=message;
    const explicit = message.contentWorkflowPosition;
    const positions = (message.outputFiles??[]).map(file=>artifactPosition(file.fileName))
      .filter((position):position is number=>position!==null);
    const legacy = message.contentPhase;
    // 同轮可同时返回正文、更新资料包等多个文件；采用本轮最晚的精确阶段，
    // 不让随附的旧资料包覆盖前序阶段的首次锚点。
    const position = typeof explicit==="number"&&Number.isInteger(explicit)&&explicit>=0&&explicit<=20 ? explicit
      : positions.length ? Math.max(...positions)
      : typeof legacy==="number"&&Number.isInteger(legacy)&&legacy>=0&&legacy<legacyPositions.length ? legacyPositions[legacy]
      : null;
    if (position===null||anchors.has(position)) continue;
    anchors.set(position,message.role==="assistant"&&precedingUser ? precedingUser.id : message.id);
  }
  return anchors;
}
