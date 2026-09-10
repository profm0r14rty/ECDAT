import { useState, type FormEvent } from 'react'
import { FlaskConical, KeyRound, Loader2, X } from 'lucide-react'

import {
  api,
  apiErrorMessage,
  type Artefact,
} from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import { truncatePath } from '@/lib/paths'
import {
  ClassicallyBrokenBadge,
  QuantumVulnerableBadge,
  RiskLevelBadge,
  StatusDash,
} from './badges'
import MoscaTimeline from './MoscaTimeline'

/** Props for {@link ArtefactDetailDialog}. */
interface ArtefactDetailDialogProps {
  /** The scan the artefact belongs to (needed for the PATCH endpoint). */
  scanId: string
  /** The artefact to inspect; `null` closes the dialog. */
  artefact: Artefact | null
  /** Close the dialog (e.g. overlay click or the close button). */
  onClose: () => void
  /** Called with the freshly re-assessed artefact after a successful PATCH. */
  onSaved: (updated: Artefact) => void
}

/** Rounds a display number, dropping an unnecessary trailing ".0". */
function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

/**
 * Detail modal for one artefact: full location, matched source text, the
 * Mosca risk assessment, the PQC recommendation, and a form to override the
 * risk engine's shelf-life / migration-time parameters via
 * `api.patchArtefact`. The updated assessment returned by the PATCH flows
 * straight back to the parent so the table row and this dialog re-render
 * in place — no page reload.
 */
export default function ArtefactDetailDialog({
  scanId,
  artefact,
  onClose,
  onSaved,
}: ArtefactDetailDialogProps) {
  const [shelfLife, setShelfLife] = useState(() =>
    artefact === null
      ? ''
      : formatNumber(artefact.risk_assessment.shelf_life_years),
  )
  const [migrationTime, setMigrationTime] = useState(() =>
    artefact === null
      ? ''
      : formatNumber(artefact.risk_assessment.migration_time_years),
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedMessage, setSavedMessage] = useState<string | null>(null)

  if (artefact === null) {
    return <Dialog open={false} onOpenChange={(open) => !open && onClose()} />
  }

  const current = artefact
  const ra = current.risk_assessment
  const rec = current.recommendation

  async function submitOverrides(overrides: {
    shelf_life_years?: number | null
    migration_time_years?: number | null
  }): Promise<void> {
    setSubmitting(true)
    setError(null)
    setSavedMessage(null)
    try {
      const updated = await api.patchArtefact(scanId, current.id, overrides)
      onSaved(updated)
      setShelfLife(formatNumber(updated.risk_assessment.shelf_life_years))
      setMigrationTime(formatNumber(updated.risk_assessment.migration_time_years))
      setSavedMessage('Override saved — risk assessment re-run.')
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    const shelf = shelfLife.trim() === '' ? null : Number(shelfLife)
    const migration = migrationTime.trim() === '' ? null : Number(migrationTime)
    if (shelf !== null && (!Number.isFinite(shelf) || shelf < 0)) {
      setError('Shelf life must be a non-negative number, or empty for the heuristic default.')
      return
    }
    if (migration !== null && (!Number.isFinite(migration) || migration < 0)) {
      setError('Migration time must be a non-negative number, or empty for the heuristic default.')
      return
    }
    void submitOverrides({
      shelf_life_years: shelf,
      migration_time_years: migration,
    })
  }

  function handleReset(): void {
    setShelfLife('')
    setMigrationTime('')
    void submitOverrides({
      shelf_life_years: null,
      migration_time_years: null,
    })
  }

return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-y-auto bg-surface border-border">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2 pr-6">
            <DialogTitle className="flex items-center gap-2 font-mono text-base text-foreground">
              {artefact.algorithm_family}
              {artefact.key_size_bits !== null && (
                <Badge variant="secondary" className="text-xs bg-muted text-muted-foreground">
                  {artefact.key_size_bits}-bit
                </Badge>
              )}
            </DialogTitle>
            <div className="flex items-center gap-2">
              <RiskLevelBadge level={ra.risk_level} />
              <Button
                variant="ghost"
                size="icon"
                onClick={onClose}
                className="text-muted-foreground hover:text-foreground hover:bg-accent/10"
              >
                <X className="size-4" />
              </Button>
            </div>
          </div>
          <DialogDescription className="flex items-center gap-2 mt-2">
            <span
              className="truncate font-mono text-sm text-foreground/80"
              title={artefact.file_path}
            >
              {truncatePath(artefact.file_path, 72)}
            </span>
            <span className="shrink-0 text-muted-foreground">
              :{artefact.line_number}
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {/* Failure-mode status — the two concepts stay visually separate. */}
          <div className="flex flex-wrap items-center gap-2">
            {artefact.quantum_vulnerable ? (
              <QuantumVulnerableBadge />
            ) : (
              <StatusDash
                label="Not vulnerable to Shor's/Grover's quantum algorithms"
                className="flex items-center gap-1.5 text-xs"
              >
                <span>Not vulnerable to Shor/Grover</span>
              </StatusDash>
            )}
            {artefact.classically_broken ? (
              <ClassicallyBrokenBadge />
            ) : (
              <StatusDash
                label="Not broken by any known classical attack"
                className="flex items-center gap-1.5 text-xs"
              >
                <span>Not classically broken</span>
              </StatusDash>
            )}
          </div>

          {/* Matched source text */}
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              Matched text
            </p>
            <pre className="overflow-x-auto rounded-md border border-border bg-bg/50 px-3 py-2 font-mono text-xs whitespace-pre-wrap break-all text-foreground">
              {artefact.matched_text}
            </pre>
          </div>

          {/* Detection metadata */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
            <MetaItem label="Language" value={artefact.language} />
            <MetaItem
              label="Confidence"
              value={`${Math.round(artefact.confidence * 100)}%`}
            />
            <MetaItem label="Method" value={artefact.detection_method} />
            <MetaItem label="Asset type" value={artefact.asset_type} />
          </div>

          {/* Mosca's inequality assessment */}
          <div className="rounded-md border border-border bg-bg/30 p-3">
            <p className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <FlaskConical className="size-3.5 text-accent" />
              Mosca's inequality — urgency = (X + Y) / Z
            </p>
            <MoscaTimeline
              risk={ra}
              classicallyBroken={artefact.classically_broken}
              quantumVulnerable={artefact.quantum_vulnerable}
            />
            <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-1 border-t border-border pt-3 text-sm">
              <MetaItem label="Shelf life (Y)" value={`${formatNumber(ra.shelf_life_years)} yr`} />
              <MetaItem label="Migration (X)" value={`${formatNumber(ra.migration_time_years)} yr`} />
              <MetaItem label="Threat horizon (Z)" value={
                artefact.classically_broken
                  ? 'N/A — already broken'
                  : `${formatNumber(ra.threat_horizon_years)} yr`
              } />
              <div className="flex items-center gap-2">
                <MetaItem label="Urgency" value={`${formatNumber(ra.urgency_ratio)}`} />
                {ra.mosca_violation && (
                  <Badge variant="destructive" className="text-xs">
                    Mosca violation
                  </Badge>
                )}
              </div>
            </div>
          </div>

          {/* PQC recommendation */}
          <div className="rounded-md border border-border bg-bg/30 p-3">
            <p className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <KeyRound className="size-3.5 text-accent" />
              Recommended migration
            </p>
            <div className="flex flex-col gap-1 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-foreground">{rec.recommended_algorithm}</span>
                {rec.fips_reference !== '' && (
                  <Badge variant="outline" className="font-mono text-xs border-border">
                    {rec.fips_reference}
                  </Badge>
                )}
              </div>
              {rec.rationale !== '' && (
                <p className="text-muted-foreground">{rec.rationale}</p>
              )}
              {rec.latency_note !== '' && (
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium">Latency:</span> {rec.latency_note}
                </p>
              )}
              {rec.migration_note !== '' && (
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium">Migration:</span> {rec.migration_note}
                </p>
              )}
            </div>
          </div>

          {/* Risk-engine override form */}
          <form
            onSubmit={handleSubmit}
            className="flex flex-col gap-3 rounded-md border border-border bg-bg/30 p-3"
          >
            <p className="text-xs font-medium text-muted-foreground">
              Override risk parameters — leave a field blank to fall back to
              the scanner's heuristic default; "Reset" clears both.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="shelf-life" className="text-xs">Shelf life (years, Y)</Label>
                <Input
                  id="shelf-life"
                  type="number"
                  min={0}
                  step={0.5}
                  value={shelfLife}
                  onChange={(event) => setShelfLife(event.target.value)}
                  placeholder="heuristic"
                  className="border-border bg-background"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="migration-time" className="text-xs">Migration time (years, X)</Label>
                <Input
                  id="migration-time"
                  type="number"
                  min={0}
                  step={0.5}
                  value={migrationTime}
                  onChange={(event) => setMigrationTime(event.target.value)}
                  placeholder="heuristic"
                  className="border-border bg-background"
                />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" disabled={submitting} size="sm" className="bg-accent text-accent-foreground hover:bg-accent-soft">
                {submitting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  'Save overrides'
                )}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={submitting}
                onClick={handleReset}
                className="border-border hover:bg-accent/5 hover:text-accent"
              >
                Reset to defaults
              </Button>
              {savedMessage !== null && (
                <span className="text-xs text-emerald-600 dark:text-emerald-400">{savedMessage}</span>
              )}
              {error !== null && (
                <span className="text-xs text-red-600 dark:text-red-400">{error}</span>
              )}
            </div>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Label + value pair used inside the dialog's grids. */
function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex flex-col">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </span>
  )
}