import type { ChatModel } from "../api";

export default function BuildVerification({ model, disabled, onVerify }: {
  model?: ChatModel; disabled: boolean; onVerify: () => void;
}) {
  return <div className="build-verification">
    <p className="muted small">
      {model?.validation_status === "passed" ? "Geometry checks passed. " : "Prompts create quick, unchecked previews. "}
      Verify Build runs the full checks and repairs using more AI credits.
    </p>
    <button type="button" className="primary" disabled={disabled || !model?.model_url}
      onClick={onVerify}>Verify Build</button>
  </div>;
}
