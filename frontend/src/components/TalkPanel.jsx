import { useRef, useState } from "react";
import { Loader2, Mic, Send, Square } from "lucide-react";
import { toast } from "sonner";
import { Button } from "./ui/button";
import { parseText, transcribe } from "../lib/api";

const CONTOH = [
  "Hari ini saya jual dua nasi goreng dan tiga es teh, total 87 ribu",
  "Pak Budi masih punya utang 150 ribu dari minggu lalu",
  "Beli ayam 3 kg 105 ribu",
  "Berapa untung saya hari ini?",
];

export const TalkPanel = ({ onDraft }) => {
  const [state, setState] = useState("idle"); // idle | listening | processing
  const [text, setText] = useState("");
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);

  const runParse = async (value) => {
    setState("processing");
    try {
      const draft = await parseText(value);
      onDraft(draft);
      setText("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memahami perintah");
    } finally {
      setState("idle");
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size < 1200) {
          setState("idle");
          toast.error("Rekaman terlalu pendek, coba lagi");
          return;
        }
        setState("processing");
        try {
          const { text: spoken } = await transcribe(blob);
          if (!spoken?.trim()) throw new Error("kosong");
          toast.success(`Terdengar: “${spoken}”`);
          await runParse(spoken);
        } catch (e) {
          setState("idle");
          toast.error("Gagal mengenali suara. Silakan ketik saja.");
        }
      };
      rec.start();
      recorderRef.current = rec;
      setState("listening");
    } catch {
      toast.error("Mikrofon tidak tersedia. Gunakan input teks di bawah.");
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setState("processing");
  };

  const busy = state === "processing";

  return (
    <section className="rounded-3xl border border-hairline bg-white p-6 shadow-card" data-testid="talk-panel">
      <div className="flex flex-col items-center">
        <div className="relative flex h-28 w-28 items-center justify-center">
          {state === "listening" && (
            <>
              <span className="vb-ring absolute h-24 w-24 rounded-full bg-forest/25" />
              <span className="vb-ring absolute h-24 w-24 rounded-full bg-forest/20" style={{ animationDelay: "0.6s" }} />
            </>
          )}
          <button
            data-testid="tap-to-talk-btn"
            disabled={busy}
            onClick={state === "listening" ? stopRecording : startRecording}
            className={`relative z-10 flex h-24 w-24 items-center justify-center rounded-full text-sand shadow-mic transition-transform duration-200 active:scale-95 ${
              state === "listening" ? "bg-terracotta" : "bg-forest hover:bg-forest-hover"
            } disabled:opacity-70`}
          >
            {busy ? (
              <Loader2 className="h-9 w-9 animate-spin" strokeWidth={2.4} />
            ) : state === "listening" ? (
              <Square className="h-8 w-8" strokeWidth={2.6} />
            ) : (
              <Mic className="h-9 w-9" strokeWidth={2.4} />
            )}
          </button>
        </div>
        <p className="mt-4 font-display text-lg font-bold text-ink" data-testid="talk-state-label">
          {state === "listening" ? "Sedang mendengar…" : busy ? "VoiceBiz sedang berpikir…" : "Tap untuk Bicara"}
        </p>
        <p className="mt-1 text-center text-xs text-mutedink">
          Bicara santai pakai Bahasa Indonesia. Contoh: “jual 2 nasi goreng total 40 ribu”.
        </p>
        {state === "listening" && (
          <div className="mt-3 flex h-6 items-end gap-1">
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <span
                key={i}
                className="vb-bar w-1.5 rounded-full bg-terracotta"
                style={{ height: "100%", animationDelay: `${i * 0.09}s` }}
              />
            ))}
          </div>
        )}
      </div>

      <div className="mt-6 flex items-center gap-2">
        <input
          data-testid="talk-text-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && text.trim() && runParse(text.trim())}
          placeholder="…atau tulis di sini"
          className="h-12 flex-1 rounded-full border border-hairline bg-sand px-5 text-sm outline-none placeholder:text-mutedink/70 focus:border-forest/40"
        />
        <Button
          data-testid="talk-send-btn"
          disabled={!text.trim() || busy}
          onClick={() => runParse(text.trim())}
          className="h-12 w-12 shrink-0 rounded-full bg-forest p-0 hover:bg-forest-hover"
        >
          <Send className="h-5 w-5" strokeWidth={2.4} />
        </Button>
      </div>

      <div className="mt-4 flex gap-2 overflow-x-auto pb-1 no-scrollbar">
        {CONTOH.map((c, i) => (
          <button
            key={i}
            data-testid={`example-chip-${i}`}
            disabled={busy}
            onClick={() => runParse(c)}
            className="shrink-0 rounded-full border border-hairline bg-sand px-4 py-2 text-xs font-medium text-mutedink transition-colors hover:border-forest/30 hover:text-forest"
          >
            {c}
          </button>
        ))}
      </div>
    </section>
  );
};
