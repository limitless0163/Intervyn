import { SessionViewSchema } from "@/types/session";
import { reportState, type ReportState } from "./report-state";

/** Poll JSON sequentially; re-render the server page only when its state changes. */
export function watchReport(
  sessionId: string,
  {
    state,
    intervalMs,
    stopAfterMs,
    isVisible,
    onChange,
    onStalled,
  }: {
    state: ReportState;
    intervalMs: number;
    stopAfterMs: number;
    isVisible: () => boolean;
    onChange: () => void;
    onStalled: () => void;
  },
): () => void {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;

  function stop() {
    controller.abort();
    clearTimeout(timer);
    clearTimeout(deadline);
  }

  const deadline = setTimeout(() => {
    stop();
    onStalled();
  }, stopAfterMs);

  async function poll() {
    if (controller.signal.aborted) return;
    if (isVisible()) {
      try {
        const res = await fetch(
          `/api/session/${encodeURIComponent(sessionId)}`,
          {
            cache: "no-store",
            signal: AbortSignal.any([
              controller.signal,
              AbortSignal.timeout(15_000),
            ]),
          },
        );
        if (controller.signal.aborted) return;
        // A failed read must not turn a real report into a sample preview.
        const parsed = res.ok
          ? SessionViewSchema.safeParse(await res.json())
          : null;
        if (controller.signal.aborted) return;
        if (
          parsed?.success &&
          parsed.data.session_id === sessionId &&
          reportState(parsed.data) !== state
        ) {
          stop();
          onChange();
          return;
        }
      } catch {
        if (controller.signal.aborted) return;
      }
    }
    timer = setTimeout(poll, intervalMs);
  }

  timer = setTimeout(poll, intervalMs);
  return stop;
}
