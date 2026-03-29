import { useState } from "react";
import { getDownloadUrl, type JobResult } from "../api/client";

interface Props {
  result: JobResult;
  onReset: () => void;
}

type Tab = "minutes" | "transcript";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function ResultViewer({ result, onReset }: Props) {
  const [tab, setTab] = useState<Tab>("minutes");
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const text = tab === "minutes" ? result.minutes : transcriptText();
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const transcriptText = () =>
    result.transcript
      .map(
        (seg) =>
          `[${formatTime(seg.start_time)} - ${formatTime(seg.end_time)}] ${seg.text}`
      )
      .join("\n");

  return (
    <div className="space-y-4">
      {/* Success banner */}
      <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
        <p className="text-green-700 font-medium">회의록 생성 완료!</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b">
        <button
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            tab === "minutes"
              ? "border-blue-500 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("minutes")}
        >
          회의록
        </button>
        <button
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            tab === "transcript"
              ? "border-blue-500 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("transcript")}
        >
          녹취록 ({result.transcript.length}개 세그먼트)
        </button>
      </div>

      {/* Content */}
      <div className="bg-gray-50 rounded-lg p-6 max-h-[60vh] overflow-y-auto text-left">
        {tab === "minutes" ? (
          <div className="prose prose-sm max-w-none whitespace-pre-wrap text-gray-800">
            {result.minutes}
          </div>
        ) : (
          <div className="space-y-2 font-mono text-sm">
            {result.transcript.map((seg, i) => (
              <div key={i} className="flex gap-3">
                <span className="text-gray-400 flex-shrink-0">
                  [{formatTime(seg.start_time)} - {formatTime(seg.end_time)}]
                </span>
                <span className="text-gray-700">{seg.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-3 justify-center">
        <button
          onClick={handleCopy}
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm"
        >
          {copied ? "복사됨!" : "복사"}
        </button>
        <a
          href={getDownloadUrl(result.jobId)}
          download
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm inline-block"
        >
          다운로드 (.md)
        </a>
        <button
          onClick={onReset}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
        >
          새로 시작
        </button>
      </div>
    </div>
  );
}
