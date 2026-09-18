import {enableModuleFileTransport} from "@frontmind/module-ui/components/file-preview-runtime";
import React from 'react';
import { createRoot } from 'react-dom/client';
import './base.css';
import ModuleWorkspace from './App';

// Local fixtures and live business components share exactly this entry.
enableModuleFileTransport();
createRoot(document.getElementById('root')!).render(<React.StrictMode><ModuleWorkspace preview={import.meta.env.DEV} /></React.StrictMode>);
