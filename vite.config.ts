import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[tailwindcss()],build:{outDir:'dist/public',emptyOutDir:true},server:{host:'127.0.0.1'},esbuild:{jsx:'automatic'}});
