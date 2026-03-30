import { useState } from "react";
import { useJob } from "./hooks/useJob";
import { FileUpload } from "./components/FileUpload";
import { ProgressTracker } from "./components/ProgressTracker";
import { ResultViewer } from "./components/ResultViewer";
import { PasscodeGate } from "./components/PasscodeGate";
import { getPasscode } from "./api/client";

export default function App() {
  const [authenticated, setAuthenticated] = useState(!!getPasscode());
  const { appState, filename, status, result, error, submit, reset, displayProgress, processingStartedAt } = useJob();

  if (!authenticated) {
    return <PasscodeGate onVerified={() => setAuthenticated(true)} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-gray-900">
            Audio to Minutes
          </h1>
          <p className="text-gray-500 mt-2">
            오디오 파일을 업로드하면 AI가 회의록을 생성합니다
          </p>
        </div>

        {/* Main card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
          {/* Idle: show upload */}
          {appState === "idle" && <FileUpload onSubmit={submit} />}

          {/* Uploading / Processing: show progress */}
          {(appState === "uploading" || appState === "processing") && (
            <ProgressTracker
              filename={filename}
              status={status}
              isUploading={appState === "uploading"}
              displayProgress={displayProgress}
              processingStartedAt={processingStartedAt}
            />
          )}

          {/* Completed: show results */}
          {appState === "completed" && result && (
            <ResultViewer result={result} onReset={reset} />
          )}

          {/* Error */}
          {appState === "error" && (
            <div className="space-y-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-700 font-medium">오류가 발생했습니다</p>
                <p className="text-red-600 text-sm mt-1">{error}</p>
              </div>
              <button
                onClick={reset}
                className="w-full py-3 px-6 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
              >
                다시 시작
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-gray-400 mt-8">
          Gemini (transcription + minutes) | Cloudflare Workers | v0.3.0
        </p>
      </div>
    </div>
  );
}
