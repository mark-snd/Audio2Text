import { useState } from "react";
import { verifyPasscode, setPasscode } from "../api/client";

interface Props {
  onVerified: () => void;
}

export function PasscodeGate({ onVerified }: Props) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;

    setLoading(true);
    setError("");

    try {
      const ok = await verifyPasscode(code.trim());
      if (ok) {
        setPasscode(code.trim());
        onVerified();
      } else {
        setError("잘못된 비밀번호입니다");
      }
    } catch {
      setError("서버 연결에 실패했습니다");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 w-full max-w-sm">
        <h1 className="text-2xl font-bold text-gray-900 text-center mb-2">
          Audio to Minutes
        </h1>
        <p className="text-gray-500 text-sm text-center mb-6">
          비밀번호를 입력하세요
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="비밀번호"
            autoFocus
            className="w-full px-4 py-3 border border-gray-300 rounded-lg text-center text-lg tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />

          {error && (
            <p className="text-red-500 text-sm text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !code.trim()}
            className="w-full py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "확인 중..." : "확인"}
          </button>
        </form>
      </div>
    </div>
  );
}
