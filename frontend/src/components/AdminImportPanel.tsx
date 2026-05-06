import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { apiRequest } from '../api/client'
import type { ImportRun } from '../types/api'

export function AdminImportPanel() {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleImport() {
    if (!file) {
      setMessage('Choose a CSV file before importing.')
      return
    }

    const formData = new FormData()
    formData.append('csv_file', file)
    setIsSubmitting(true)
    setMessage(null)

    try {
      const result = await apiRequest<ImportRun>('/imports/csv', {
        method: 'POST',
        body: formData,
      })
      setMessage(
        `Import #${result.id} completed: ${result.rows_processed} rows processed, ${result.rows_changed} term rows changed, ${result.duplicates_dropped} duplicate rows dropped.`,
      )
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['sports'] }),
        queryClient.invalidateQueries({ queryKey: ['terms'] }),
        queryClient.invalidateQueries({ queryKey: ['roster'] }),
      ])
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : 'Import failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="panel import-panel">
      <div>
        <p className="panel-label">Admin Import</p>
        <h3>Manual CSV upload</h3>
        <p>
          Phase 1 uses a manual source-of-truth import. The importer reads UTF-8 with BOM, drops
          duplicate Rocket IDs using last-row-wins, and logs blank cohorts.
        </p>
      </div>

      <div className="import-controls">
        <input
          type="file"
          accept=".csv"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <button type="button" className="primary-button" onClick={handleImport} disabled={isSubmitting}>
          {isSubmitting ? 'Importing...' : 'Run import'}
        </button>
      </div>

      {message ? <p className="import-message">{message}</p> : null}
    </section>
  )
}

