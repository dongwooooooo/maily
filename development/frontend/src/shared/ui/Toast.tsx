import { X } from 'lucide-react'
import { toastCopy } from '@/features/briefing/data/briefing.mock'

interface ToastProps {
  show: boolean
  onUndo?: () => void
  onClose: () => void
  message?: string
}

/** Undo toast, auto-hide handled by parent. Omit `onUndo` for a confirmation-only toast (no undo action left to take). */
function Toast({ show, onUndo, onClose, message = toastCopy.message }: ToastProps) {
  return (
    <div className="toast" data-show={show ? 'true' : 'false'} role="status" aria-live="polite">
      <span>{message}</span>
      {onUndo && (
        <button type="button" onClick={onUndo}>
          {toastCopy.undo}
        </button>
      )}
      <button type="button" className="toast-close" onClick={onClose} aria-label={toastCopy.close}>
        <X size={18} strokeWidth={1.8} aria-hidden="true" />
      </button>
    </div>
  )
}

export default Toast
