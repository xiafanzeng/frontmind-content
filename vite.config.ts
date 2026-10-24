import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import {localWorkflowPlugin} from './standalone/local-workflow';
const localRoot=process.env.FRONTMIND_LOCAL_WORKFLOW_ROOT;
const configDir=process.env.FRONTMIND_LOCAL_CONFIG_DIR;
if(Boolean(localRoot)!==Boolean(configDir))throw new Error('真实本地模式需同时设置 FRONTMIND_LOCAL_WORKFLOW_ROOT 和 FRONTMIND_LOCAL_CONFIG_DIR');
export default defineConfig({plugins:[tailwindcss(),localWorkflowPlugin(localRoot&&configDir?{root:localRoot,configDir,python:process.env.FRONTMIND_PYTHON||'python3'}:undefined)],define:{'import.meta.env.VITE_LOCAL_WORKFLOW':JSON.stringify(Boolean(localRoot))},build:{outDir:'dist/public',emptyOutDir:true},server:{host:'127.0.0.1',proxy:localRoot?undefined:{'/api':{target:'http://127.0.0.1:5174',changeOrigin:false}}},esbuild:{jsx:'automatic'}});
