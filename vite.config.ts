import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import {localWorkflowPlugin} from './standalone/local-workflow';
const localRoot=process.env.FRONTMIND_LOCAL_WORKFLOW_ROOT;
const configDir=process.env.FRONTMIND_LOCAL_CONFIG_DIR;
const realBackendBridge=process.env.FRONTMIND_REAL_BACKEND_BRIDGE==='1';
if(Boolean(localRoot)!==Boolean(configDir))throw new Error('真实本地模式需同时设置 FRONTMIND_LOCAL_WORKFLOW_ROOT 和 FRONTMIND_LOCAL_CONFIG_DIR');
if(realBackendBridge&&localRoot)throw new Error('仅收件桥和本地生成工作流不能同时启用；请明确选择一种运行模式');
export default defineConfig({plugins:[tailwindcss(),localWorkflowPlugin(localRoot&&configDir?{root:localRoot,configDir,python:process.env.FRONTMIND_PYTHON||'python3'}:undefined)],define:{'import.meta.env.VITE_LOCAL_WORKFLOW':JSON.stringify(Boolean(localRoot))},build:{outDir:'dist/public',emptyOutDir:true},server:{host:'127.0.0.1',proxy:realBackendBridge?{'/api':{target:'http://127.0.0.1:5174',changeOrigin:false}}:undefined},esbuild:{jsx:'automatic'}});
