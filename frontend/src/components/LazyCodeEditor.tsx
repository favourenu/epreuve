import { lazy, Suspense, type ComponentProps } from 'react'

const CodeEditorImpl = lazy(() => import('./CodeEditor').then((m) => ({ default: m.CodeEditor })))

export function CodeEditor(props: ComponentProps<typeof CodeEditorImpl>) {
  return (
    <Suspense fallback={<div className="editor-frame editor-loading" style={{ height: props.height ?? 380 }} />}>
      <CodeEditorImpl {...props} />
    </Suspense>
  )
}
