/// <reference types="vite/client" />
/// 

declare module 'react-dom' {
    export function flushSync(fn: () => R): R;
  }