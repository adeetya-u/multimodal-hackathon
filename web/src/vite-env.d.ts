/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE: string;
  readonly VITE_VAPI_PUBLIC_KEY: string;
  readonly VITE_VAPI_OR_ASSISTANT_ID: string;
  readonly VITE_VAPI_INTRO_ASSISTANT_ID: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
