import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { errorMessage } from '@/lib/api'

/** Mutation that toasts success/failure and refreshes every query (operational data is interlinked). */
export function useAction<TData, TVars = void>(
  fn: (v: TVars) => Promise<TData>,
  opts: { success?: string | ((d: TData) => string); onSuccess?: (d: TData) => void } = {},
) {
  const qc = useQueryClient()
  return useMutation<TData, Error, TVars>({
    mutationFn: fn,
    onSuccess: (d) => {
      if (opts.success) toast.success(typeof opts.success === 'function' ? opts.success(d) : opts.success)
      void qc.invalidateQueries()
      opts.onSuccess?.(d)
    },
    onError: (e) => { toast.error(errorMessage(e)) },
  })
}
