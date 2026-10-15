export const updatesDisabledMessage = 'Updates are disabled in this Flexpair build.'

export function updateAllRefusal<Kind extends string>(
  connections: { id: string; label: string; kind: Kind }[],
  excludeIds: string[] = []
) {
  const excluded = new Set(excludeIds)

  return {
    ok: false,
    results: connections
      .filter(connection => !excluded.has(connection.id))
      .map(connection => ({
        connectionId: connection.id,
        label: connection.label,
        kind: connection.kind,
        ok: false,
        skipped: true,
        reason: 'updates-disabled',
        detail: updatesDisabledMessage
      }))
  }
}
