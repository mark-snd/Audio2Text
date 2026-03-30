import { useState, useRef, type DragEvent } from "react";
import type { EventMeta } from "../api/client";

interface Props {
  onSubmit: (file: File, eventMeta?: EventMeta) => void;
  disabled?: boolean;
}

const SUPPORTED = [".wav", ".mp3", ".aiff", ".aac", ".ogg", ".flac", ".m4a"];

export function FileUpload({ onSubmit, disabled }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [showMeta, setShowMeta] = useState(false);
  const [eventName, setEventName] = useState("");
  const [date, setDate] = useState("");
  const [speakers, setSpeakers] = useState("");
  const [terminology, setTerminology] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    const ext = "." + f.name.split(".").pop()?.toLowerCase();
    if (!SUPPORTED.includes(ext)) {
      alert(`지원하지 않는 형식입니다.\n지원 형식: ${SUPPORTED.join(", ")}`);
      return;
    }
    setFile(f);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleSubmit = () => {
    if (!file) return;

    let eventMeta: EventMeta | undefined;
    if (showMeta && (eventName || date || speakers || terminology)) {
      eventMeta = {};
      if (eventName) eventMeta.event_name = eventName;
      if (date) eventMeta.date = date;
      if (speakers) {
        eventMeta.speakers = speakers
          .split("\n")
          .filter(Boolean)
          .map((line) => {
            const [name, role] = line.split(",").map((s) => s.trim());
            return { name: name || "", role: role || "" };
          });
      }
      if (terminology) {
        eventMeta.terminology = terminology
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
      }
    }

    onSubmit(file, eventMeta);
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      {/* Drop zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-blue-500 bg-blue-50"
            : file
              ? "border-green-400 bg-green-50"
              : "border-gray-300 hover:border-gray-400"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept={SUPPORTED.join(",")}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />

        {file ? (
          <div>
            <div className="text-3xl mb-2">&#127925;</div>
            <p className="text-lg font-medium text-gray-800">{file.name}</p>
            <p className="text-sm text-gray-500 mt-1">{formatSize(file.size)}</p>
            <p className="text-sm text-blue-500 mt-2">
              클릭하여 다른 파일 선택
            </p>
          </div>
        ) : (
          <div>
            <div className="text-4xl mb-3">&#128194;</div>
            <p className="text-lg text-gray-600">
              파일을 드래그하거나 클릭하여 업로드
            </p>
            <p className="text-sm text-gray-400 mt-2">
              지원 형식: {SUPPORTED.join(", ")} | 최대 100MB
            </p>
          </div>
        )}
      </div>

      {/* Event metadata (optional, collapsible) */}
      <div>
        <button
          type="button"
          className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
          onClick={() => setShowMeta(!showMeta)}
        >
          <span className={`transition-transform ${showMeta ? "rotate-90" : ""}`}>
            &#9654;
          </span>
          회의 정보 추가 (선택사항)
        </button>

        {showMeta && (
          <div className="mt-3 space-y-3 p-4 bg-gray-50 rounded-lg text-left">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                회의 제목
              </label>
              <input
                type="text"
                value={eventName}
                onChange={(e) => setEventName(e.target.value)}
                placeholder="예: AI 적용 방안 논의"
                className="w-full px-3 py-2 border rounded-md text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                날짜
              </label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full px-3 py-2 border rounded-md text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                참석자 (한 줄에 한 명: 이름, 역할)
              </label>
              <textarea
                value={speakers}
                onChange={(e) => setSpeakers(e.target.value)}
                placeholder={"Victor, Product Manager\nPatrick, Engineer"}
                rows={3}
                className="w-full px-3 py-2 border rounded-md text-sm font-mono"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                전문 용어 (쉼표 구분)
              </label>
              <input
                type="text"
                value={terminology}
                onChange={(e) => setTerminology(e.target.value)}
                placeholder="GA4, YES24, SNDWorks"
                className="w-full px-3 py-2 border rounded-md text-sm"
              />
            </div>
          </div>
        )}
      </div>

      {/* Minutes engine info */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-600 whitespace-nowrap">회의록 AI:</span>
        <div className="flex-1 py-2 px-3 text-sm font-medium rounded-lg border bg-blue-50 border-blue-500 text-blue-700">
          Gemini
          <span className="block text-xs font-normal opacity-70">빠름 · 저렴</span>
        </div>
      </div>

      {/* Submit button */}
      <button
        onClick={handleSubmit}
        disabled={!file || disabled}
        className="w-full py-3 px-6 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
      >
        회의록 생성 시작
      </button>
    </div>
  );
}
