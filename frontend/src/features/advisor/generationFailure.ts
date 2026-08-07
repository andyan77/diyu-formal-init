import type { FailureDiagnostic } from "../../app/types";
import { ContentStreamContractError } from "../../shared/contracts/contentStream";
import { ApiError } from "../../services/api";

/**
 * What to say when a generation does not finish.
 *
 * A failed run has three quite different causes and they must not collapse
 * into one apology, because the person's next move differs each time: the
 * stream contradicted the contract it publishes (nothing it carried can be
 * trusted), the server answered with a diagnosed error (it already told us
 * which stage and whether retrying helps), or the network simply stopped.
 *
 * Kept out of the workspace component so the wording and the retry advice can
 * be read — and asserted — without going through a render.
 */

export interface StreamFailure {
  message: string;
  diagnostic: FailureDiagnostic;
  /**
   * True only for a contract breach: the progress trail belongs to a stream
   * that lied, so it is withheld along with the result.
   */
  discardStages: boolean;
}

export function transportDiagnostic(action: string): FailureDiagnostic {
  return { stage: "transport", retryable: true, action, traceId: "" };
}

function serverDiagnostic(reason: ApiError): FailureDiagnostic {
  return {
    stage: reason.failureStage,
    retryable: reason.retryable,
    action: reason.action,
    traceId: reason.traceId
  };
}

export function describeStreamFailure(reason: unknown): StreamFailure {
  if (reason instanceof ContentStreamContractError) {
    return {
      message: reason.message,
      diagnostic: {
        stage: "contract",
        retryable: true,
        action: "输入已经保留，可以使用原输入重试。",
        traceId: ""
      },
      discardStages: true
    };
  }
  if (reason instanceof ApiError) {
    return {
      message: `${reason.message} 输入和已有成品都已保留。`,
      diagnostic: serverDiagnostic(reason),
      discardStages: false
    };
  }
  return {
    message: "网络没有完成这次请求。输入和已有成品都已保留，可以恢复后重试。",
    diagnostic: transportDiagnostic("网络恢复后可以使用原输入重试。"),
    discardStages: false
  };
}

/**
 * A revision failed, so the words are about the requirement and the versions
 * already on screen — not about "输入和已有成品", which is the first-draft story.
 */
export function describeRevisionFailure(reason: unknown): {
  message: string;
  diagnostic: FailureDiagnostic;
} {
  if (reason instanceof ApiError) {
    return {
      message: `${reason.message} 你的要求和已有版本都已保留。`,
      diagnostic: serverDiagnostic(reason)
    };
  }
  return {
    message: "这次修改没有完成。你的要求和已有版本都已保留，可以安全重试。",
    diagnostic: transportDiagnostic("网络恢复后可以使用同一修改要求重试。")
  };
}
