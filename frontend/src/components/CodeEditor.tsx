import Editor, { loader } from '@monaco-editor/react'
// Only the editor core + Python highlighting, not all of Monaco's languages.
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api'
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { useEffect, useState } from 'react'

// Bundle Monaco locally instead of loading it from a CDN, so tests work offline.
self.MonacoEnvironment = { getWorker: () => new editorWorker() }
loader.config({ monaco })

function usePrefersDark() {
  const query = '(prefers-color-scheme: dark)'
  const [dark, setDark] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = (e: MediaQueryListEvent) => setDark(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return dark
}

interface Props {
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
  height?: number | string
}

export function CodeEditor({ value, onChange, readOnly = false, height = 380 }: Props) {
  const dark = usePrefersDark()
  return (
    <div className="editor-frame">
      <Editor
        height={height}
        language="python"
        theme={dark ? 'vs-dark' : 'light'}
        value={value}
        onChange={(v) => onChange?.(v ?? '')}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 14,
          tabSize: 4,
          insertSpaces: true,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          wordWrap: 'on',
          // Real coding screens usually don't offer autocomplete; keep it honest.
          quickSuggestions: false,
          suggestOnTriggerCharacters: false,
        }}
      />
    </div>
  )
}
