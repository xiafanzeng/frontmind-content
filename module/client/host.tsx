import {createContext,useContext,type ComponentType,type ReactNode} from "react";
import type {ContentProductionDto,ContentProductionInput,ContentProductionAction} from "../contracts/content-production";
export type ContentOutputFile={fileUrl:string;fileName:string;mimeType:string};
export type ContentMessage={id:string;role:"user"|"assistant";content:string;timestamp:number;outputFiles?:ContentOutputFile[];attachments?:{id:string;type:"file"|"image";name:string;fileId?:string}[];generalChatDispatch?:Record<string,unknown>};
export type ContentConversation={id:string;title:string;purpose?:"content_production"|"enterprise_qa";taskId?:string;previousResponseId?:string;status:string;messages:ContentMessage[];createdAt:number;updatedAt:number;executionKind?:"general_chat_v2"|"response_logic"};
export type TaskResponse={id:string;purpose?:"content_production"|"enterprise_qa"|"general";status:string;contentProduction?:ContentProductionDto|null;output?:unknown[];metadata?:{task_title?:string};error?:{message?:string}};
export type ContentSendOptions={purpose?:"content_production";contentProduction?:ContentProductionInput;contentProductionAction?:ContentProductionAction};
export interface ContentConversationApi {
 state:{conversations:ContentConversation[]};activeConversation:ContentConversation|null;hydrated:boolean;
 createConversation(options:{title:string;reuseEmpty:false;purpose:"content_production"}):string;
 setActive(id:string):void;deleteConversation(id:string):void;
}
export type ContentHomeProps={embedded?:boolean;operatorWorkspace?:boolean;knowledgeEditingBlocked?:boolean;hideSidebar?:boolean;hidePortalNavigation?:boolean;showKnowledgeBaseStarter?:boolean;showAccountMenu?:boolean;showSettings?:boolean;purpose:"content_production";contentProduction?:ContentProductionInput;standardWelcomeVariant?:"simple";conversationFooter?:ReactNode};
export type ContentToolbarProps={tasks:ContentConversation[];currentId?:string;onNew():void;onSelect(id:string):void;onDelete(id:string):void;disabled:boolean;presentation:"panel";labels:{newAction:string;history:string;noun:string}};
export interface ContentWorkspaceHost {
 connections?:{publishedKnowledge?:boolean};
 ConversationPurposeProvider:ComponentType<{purpose:"content_production";children:ReactNode}>;
 useConversation():ContentConversationApi;
 useSendMessage():{sendMessage(prompt:string,files?:File[],options?:ContentSendOptions):Promise<boolean|void>};
 retrieveTask(id:string,options?:{signal?:AbortSignal}):Promise<TaskResponse>;
 captureWorkspaceRestOperation(signal?:AbortSignal):{signal:AbortSignal;assertActive():void;fetch:typeof fetch};
 useWorkspaceDraftGuard(input:{dirty:boolean;label:string}):void;
 requestWorkspaceNavigation(operation:()=>void):void;
 Home:ComponentType<ContentHomeProps>;
 FilePreview:ComponentType<{file:{id:string;type:"file";name:string;blobUrl:string};className?:string}>;
 WorkbenchTaskToolbar:ComponentType<ContentToolbarProps>;
 AgentWorkbenchShell:ComponentType<{embedded:boolean;projectId:string;moduleId:string;title:string;resultTitle:string;taskTitle:string;taskKey:string;scrollMain:boolean;showResult:boolean;topbarActions:ReactNode;main:ReactNode;auxiliary:ReactNode;resultKey:string;status:string}>;
 BusinessWorkspaceInspector:ComponentType<{summary:{status:string;items:{label:string;value:string}[];outputs:{id:string;title:string;type:string;status:string;onOpen():void}[]}}>;
}
const Context=createContext<ContentWorkspaceHost|null>(null);
export const ContentWorkspaceHostProvider=Context.Provider;
export function useContentWorkspaceHost(){const host=useContext(Context);if(!host)throw new Error("Content module host is not installed");return host;}
