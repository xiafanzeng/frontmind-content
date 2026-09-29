import {describe,it,expect,vi,afterEach} from 'vitest';
import {assertContentTaskAction,ContentTaskError} from '../server/task-handlers';
import {contentArtifactPolicy,contentProductionClientOptions,isContentWorkflowStateFilename} from '../server/runtime';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
const directories:string[]=[];
afterEach(()=>{vi.unstubAllEnvs();for(const path of directories.splice(0))rmSync(path,{recursive:true,force:true});});
describe('content-owned transport policies',()=>{
 it('does not reinterpret ordinary task messages as content confirmation',()=>{
  expect(()=>assertContentTaskAction(undefined,undefined)).not.toThrow();
  expect(()=>assertContentTaskAction('enterprise_qa',{kind:'confirm_blueprint',revision:3} as any)).toThrow(ContentTaskError);
  expect(()=>assertContentTaskAction('content_production',{kind:'confirm_blueprint',revision:3} as any)).not.toThrow();
 });
 it('hides snapshots only for content tasks and preserves explicit presentation downloads',()=>{
  expect(contentArtifactPolicy('content_production','frontmind_workflow_job_snapshot_123.zip','zh')).toEqual({hidden:true,chinesePresentation:true});
  expect(contentArtifactPolicy(undefined,'frontmind_workflow_job_snapshot_123.zip','zh')).toEqual({hidden:false,chinesePresentation:false});
  expect(contentArtifactPolicy('content_production','article.md',undefined)).toEqual({hidden:false,chinesePresentation:false});
 });
 it('retains the original workflow binding and action revision in execution options',()=>{
  const root=mkdtempSync(join(tmpdir(),'content-policy-'));directories.push(root);
  const bytes=Buffer.from('synthetic workflow bytes');const binding={filename:'workflow-test.zip',rootDirectory:'workflow',version:'4.11.0',sha256:createHash('sha256').update(bytes).digest('hex')};
  writeFileSync(join(root,binding.filename),bytes);vi.stubEnv('FRONTMIND_CONTENT_WORKFLOW_DIR',root);
  const context={revision:1,accountUserId:1,enterpriseProjectId:null,purpose:'content_production',knowledgeBase:null,knowledgeText:null,contentProduction:{mode:'single_article',knowledgeSource:'manual',monitoringAnswerAssetIds:[]},contentWorkflow:binding,inputFiles:[]} as any;
  const action={kind:'confirm_blueprint',revision:17} as const;
  const options=contentProductionClientOptions(context,action);
  expect(options.turnContext).toContain(JSON.stringify(action));
  expect(options.systemAttachments[0].filename).toBe(context.contentWorkflow.filename);
  expect(options.recoverableStatusArtifact).toBe(isContentWorkflowStateFilename);
 });
});
