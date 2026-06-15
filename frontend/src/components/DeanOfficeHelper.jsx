import { useState, useCallback, useRef, useEffect } from "react";

const API_BASE = (
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000"
).replace(/\/+$/, ""); // sondaki "/" temizlenir (Render URL'i yanlışlıkla / ile girilebilir)

const REQUEST_TIMEOUT_MS = 90_000;

// ── Severity config ──
const SEV = {
  error:   { label: "Hata",  color: "#ef4444", bg: "rgba(239,68,68,0.08)",   border: "rgba(239,68,68,0.25)",   icon: "✕" },
  warning: { label: "Uyarı", color: "#f59e0b", bg: "rgba(245,158,11,0.08)",  border: "rgba(245,158,11,0.25)",  icon: "△" },
  info:    { label: "Bilgi", color: "#06b6d4",  bg: "rgba(6,182,212,0.08)",   border: "rgba(6,182,212,0.25)",   icon: "○" },
};

const LAYER_LABELS = { A: "Kural Motoru", B: "RAG Kontrol", C: "Semantik Analiz" };

// ── HTTP helpers ──────────────────────────────────────────────────────────────

async function analyzeDocument(file, mode, signal) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/analyze?mode=${encodeURIComponent(mode)}`, {
    method: "POST", body: formData, signal,
  });
  if (!res.ok) {
    let detail = `Sunucu hatası (HTTP ${res.status})`;
    try { const b = await res.json(); if (b.detail) detail = b.detail; } catch { try { detail = await res.text(); } catch { } }
    throw new Error(detail);
  }
  return res.json();
}

// ── StatusDot ────────────────────────────────────────────────────────────────

function StatusDot({ active, loading, pulse }) {
  if (loading) return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      border: "1.5px solid #475569", borderTopColor: "#94a3b8",
      animation: "spin 0.8s linear infinite",
    }} />
  );
  return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      background: active === "ok"      ? "#22c55e" :
                  active === "warning" ? "#f59e0b" :
                  active === false     ? "#ef4444" : "#475569",
      boxShadow: (active === "ok" && pulse)
        ? "0 0 0 3px rgba(34,197,94,0.2)"
        : "none",
      flexShrink: 0,
    }} />
  );
}

// ── SystemStatus panel ────────────────────────────────────────────────────────

function SystemStatus() {
  const [status, setStatus]         = useState(null);
  const [backendOk, setBackendOk]   = useState(null);
  const [apiCheck, setApiCheck]     = useState(null);
  const [checking, setChecking]     = useState(false);
  const [expanded, setExpanded]     = useState(false);
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [keyInput, setKeyInput]     = useState("");
  const [providerInput, setProvider] = useState("gemini");
  const [saving, setSaving]         = useState(false);
  const [saveResult, setSaveResult] = useState(null);

  // Sayfa yüklenince /status çek
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/status`, { signal: AbortSignal.timeout(5000) });
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) { setStatus(data); setBackendOk(true); }
      } catch {
        if (!cancelled) setBackendOk(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const testApiKey = useCallback(async () => {
    setChecking(true);
    setApiCheck(null);
    try {
      const res = await fetch(`${API_BASE}/check-api-key`, { signal: AbortSignal.timeout(20000) });
      const data = await res.json();
      setApiCheck(data);
    } catch {
      setApiCheck({ ok: false, error: "Sunucuya ulaşılamadı", error_type: "network" });
    } finally {
      setChecking(false);
    }
  }, []);

  const saveApiKey = useCallback(async () => {
    if (!keyInput.trim()) return;
    setSaving(true);
    setSaveResult(null);
    try {
      const res = await fetch(`${API_BASE}/admin/set-api-key`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: providerInput, api_key: keyInput.trim() }),
        signal: AbortSignal.timeout(25000),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveResult({ ok: false, error: data.detail || "Kaydetme başarısız" });
      } else {
        setSaveResult({ ok: true, message: data.message });
        setKeyInput("");
        setShowKeyForm(false);
        // Status'ı yenile
        const sr = await fetch(`${API_BASE}/status`).then(r => r.json()).catch(() => null);
        if (sr) setStatus(sr);
        setApiCheck(null);
      }
    } catch (e) {
      setSaveResult({ ok: false, error: "Sunucuya ulaşılamadı" });
    } finally {
      setSaving(false);
    }
  }, [keyInput, providerInput]);

  // Genel backend durumu: null=loading, false=down, true=up
  const layers = status?.layers;
  const layerC = layers?.C;

  // API key durumu — önce canlı test sonucuna bak, yoksa /status'a
  // quota_exceeded: key geçerli ama proje limiti dolmuş (sarı)
  let apiKeyState = "unknown";
  if (apiCheck) {
    if (apiCheck.ok) apiKeyState = "ok";
    else if (apiCheck.error_type === "quota_exceeded") apiKeyState = "warning";
    else apiKeyState = false;
  } else if (layerC) {
    if (layerC.quota_state === "quota_exceeded") apiKeyState = "warning";
    else apiKeyState = layerC.active ? "ok" : false;
  }

  const apiKeyLabel =
    apiCheck?.ok                                ? `Aktif — ${apiCheck.provider}/${apiCheck.model}` :
    apiCheck?.error_type === "quota_exceeded"   ? "Kota dolmuş — anahtar geçerli, limit bitti" :
    apiCheck?.error_type === "invalid_key"      ? "Geçersiz anahtar" :
    apiCheck?.error_type === "no_key"           ? "Yapılandırılmamış" :
    apiCheck?.error                             ? apiCheck.error.slice(0, 60) :
    layerC?.quota_state === "quota_exceeded"    ? "Kota dolmuş — anahtar geçerli, limit bitti" :
    layerC?.active                              ? `Yapılandırılmış — ${layerC.provider}/${layerC.model}` :
    layerC                                      ? "Yapılandırılmamış" : "—";

  return (
    <div style={{
      background: "rgba(255,255,255,0.02)",
      border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: 12, overflow: "hidden",
    }}>
      {/* Header row — always visible */}
      <button
        onClick={() => setExpanded(v => !v)}
        style={{
          width: "100%", padding: "12px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          background: "none", border: "none", cursor: "pointer", color: "inherit",
          fontFamily: "inherit",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <StatusDot active={backendOk === null ? "unknown" : backendOk ? "ok" : false} loading={backendOk === null} pulse />
          <span style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.04em" }}>
            SİSTEM DURUMU
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {/* Mini badges */}
          {["A","B","C"].map(k => (
            <span key={k} style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 4, fontWeight: 600,
              fontFamily: "monospace",
              background: layers?.[k]?.active ? "rgba(34,197,94,0.1)" : backendOk === false ? "rgba(239,68,68,0.1)" : "rgba(255,255,255,0.04)",
              color:      layers?.[k]?.active ? "#4ade80"              : backendOk === false ? "#f87171"             : "#475569",
              border: `1px solid ${layers?.[k]?.active ? "rgba(34,197,94,0.2)" : backendOk === false ? "rgba(239,68,68,0.2)" : "rgba(255,255,255,0.06)"}`,
            }}>
              {k}
            </span>
          ))}
          <span style={{ fontSize: 14, color: "#475569", transition: "transform 0.2s", transform: expanded ? "rotate(180deg)" : "none" }}>▾</span>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>

          {/* Backend bağlantısı */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 12px", borderRadius: 8,
            background: backendOk ? "rgba(34,197,94,0.05)" : backendOk === false ? "rgba(239,68,68,0.05)" : "rgba(255,255,255,0.02)",
            border: `1px solid ${backendOk ? "rgba(34,197,94,0.15)" : backendOk === false ? "rgba(239,68,68,0.15)" : "rgba(255,255,255,0.06)"}`,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <StatusDot active={backendOk === null ? "unknown" : backendOk ? "ok" : false} loading={backendOk === null} />
              <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>Backend</span>
            </div>
            <span style={{ fontSize: 11, color: backendOk ? "#4ade80" : backendOk === false ? "#f87171" : "#475569", fontFamily: "monospace" }}>
              {backendOk === null ? "bağlanıyor…" : backendOk ? `${API_BASE} ✓` : `${API_BASE} — ulaşılamıyor`}
            </span>
          </div>

          {/* Katman satırları */}
          {[
            { key: "A", icon: "⚙", color: "#a78bfa" },
            { key: "B", icon: "🗄", color: "#38bdf8" },
          ].map(({ key, icon, color }) => (
            <div key={key} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "9px 12px", borderRadius: 8,
              background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusDot active={layers?.[key]?.active ? "ok" : layers ? false : "unknown"} loading={!layers} />
                <span style={{ fontSize: 12, color, fontWeight: 700, fontFamily: "monospace" }}>Katman {key}</span>
                <span style={{ fontSize: 11, color: "#64748b" }}>{LAYER_LABELS[key]}</span>
              </div>
              <span style={{ fontSize: 11, color: layers?.[key]?.active ? "#4ade80" : "#f87171", fontFamily: "monospace" }}>
                {layers ? (layers[key]?.active ? layers[key].detail : layers[key]?.detail) : "—"}
              </span>
            </div>
          ))}

          {/* Katman C — API anahtarı ile birlikte */}
          <div style={{
            padding: "10px 12px", borderRadius: 8,
            background: "rgba(255,255,255,0.02)",
            border: `1px solid ${
              apiKeyState === "ok"      ? "rgba(34,197,94,0.2)"  :
              apiKeyState === "warning" ? "rgba(245,158,11,0.2)" :
              apiKeyState === false     ? "rgba(239,68,68,0.2)"  : "rgba(255,255,255,0.06)"
            }`,
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusDot active={apiKeyState} loading={checking} />
                <span style={{ fontSize: 12, color: "#fb923c", fontWeight: 700, fontFamily: "monospace" }}>Katman C</span>
                <span style={{ fontSize: 11, color: "#64748b" }}>Semantik Analiz (LLM)</span>
              </div>
              <span style={{
                fontSize: 11, fontFamily: "monospace",
                color: apiKeyState === "ok" ? "#4ade80" : apiKeyState === "warning" ? "#fbbf24" : apiKeyState === false ? "#f87171" : "#475569",
              }}>
                {checking ? "test ediliyor…" : apiKeyLabel}
              </span>
            </div>

            {/* Buton grubu: Test + Değiştir */}
            <div style={{ display: "flex", gap: 6 }}>
              <button
                onClick={testApiKey}
                disabled={checking || !backendOk}
                style={{
                  flex: 1, padding: "8px 0", borderRadius: 7,
                  background: checking ? "rgba(255,255,255,0.03)" : "rgba(251,146,60,0.08)",
                  border: `1px solid ${checking ? "rgba(255,255,255,0.06)" : "rgba(251,146,60,0.2)"}`,
                  color: checking || !backendOk ? "#475569" : "#fb923c",
                  fontSize: 12, fontWeight: 600, cursor: checking || !backendOk ? "not-allowed" : "pointer",
                  fontFamily: "inherit", transition: "all 0.2s",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                }}
              >
                {checking
                  ? <><span style={{ width: 12, height: 12, border: "1.5px solid #475569", borderTopColor: "#94a3b8", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />Test ediliyor…</>
                  : "🔑 Test Et"
                }
              </button>
              <button
                onClick={() => { setShowKeyForm(v => !v); setSaveResult(null); }}
                disabled={!backendOk}
                style={{
                  flex: 1, padding: "8px 0", borderRadius: 7,
                  background: showKeyForm ? "rgba(99,102,241,0.12)" : "rgba(255,255,255,0.04)",
                  border: `1px solid ${showKeyForm ? "rgba(99,102,241,0.3)" : "rgba(255,255,255,0.08)"}`,
                  color: !backendOk ? "#475569" : showKeyForm ? "#a5b4fc" : "#94a3b8",
                  fontSize: 12, fontWeight: 600, cursor: !backendOk ? "not-allowed" : "pointer",
                  fontFamily: "inherit", transition: "all 0.2s",
                }}
              >
                ✏️ Anahtarı Değiştir
              </button>
            </div>

            {/* Test sonucu */}
            {apiCheck && !showKeyForm && (
              <div style={{
                marginTop: 6, padding: "10px 12px", borderRadius: 6, fontSize: 11,
                background: apiCheck.ok ? "rgba(34,197,94,0.06)" : apiCheck.error_type === "quota_exceeded" ? "rgba(245,158,11,0.06)" : "rgba(239,68,68,0.06)",
                color: apiCheck.ok ? "#86efac" : apiCheck.error_type === "quota_exceeded" ? "#fcd34d" : "#fca5a5",
                lineHeight: 1.6,
              }}>
                <div style={{ fontFamily: "monospace" }}>
                  {apiCheck.ok ? `✓ Bağlantı başarılı — "${apiCheck.response_preview}"` : `✗ ${apiCheck.error}`}
                </div>
                {apiCheck.tip && (
                  <div style={{ marginTop: 6, color: "#94a3b8", fontSize: 10, lineHeight: 1.6 }}>
                    💡 {apiCheck.tip}
                  </div>
                )}
              </div>
            )}

            {/* Key değiştirme formu */}
            {showKeyForm && (
              <div style={{
                marginTop: 6, padding: "12px", borderRadius: 8,
                background: "rgba(99,102,241,0.05)", border: "1px solid rgba(99,102,241,0.15)",
                display: "flex", flexDirection: "column", gap: 8,
              }}>
                <div style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600, letterSpacing: "0.04em" }}>
                  SAĞLAYICI
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {["gemini", "groq"].map(p => (
                    <button
                      key={p}
                      onClick={() => setProvider(p)}
                      style={{
                        flex: 1, padding: "6px 0", borderRadius: 6,
                        background: providerInput === p ? "rgba(99,102,241,0.2)" : "rgba(255,255,255,0.03)",
                        border: `1px solid ${providerInput === p ? "rgba(99,102,241,0.4)" : "rgba(255,255,255,0.08)"}`,
                        color: providerInput === p ? "#a5b4fc" : "#64748b",
                        fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "monospace",
                        transition: "all 0.15s",
                      }}
                    >
                      {p === "gemini" ? "Google Gemini" : "Groq / Llama"}
                    </button>
                  ))}
                </div>
                <div style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600, letterSpacing: "0.04em", marginTop: 2 }}>
                  API ANAHTARI
                </div>
                <input
                  type="password"
                  value={keyInput}
                  onChange={e => setKeyInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && saveApiKey()}
                  placeholder={providerInput === "gemini" ? "AIzaSy…" : "gsk_…"}
                  style={{
                    padding: "9px 12px", borderRadius: 7, fontSize: 12,
                    background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
                    color: "#e2e8f0", outline: "none", fontFamily: "monospace",
                    letterSpacing: "0.05em",
                  }}
                />
                <div style={{ fontSize: 10, color: "#475569", lineHeight: 1.5 }}>
                  {providerInput === "gemini"
                    ? "aistudio.google.com/app/apikey adresinden ücretsiz alınabilir"
                    : "console.groq.com adresinden ücretsiz alınabilir"}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    onClick={saveApiKey}
                    disabled={saving || !keyInput.trim()}
                    style={{
                      flex: 1, padding: "9px 0", borderRadius: 7,
                      background: saving || !keyInput.trim() ? "rgba(255,255,255,0.03)" : "linear-gradient(135deg, #6366f1, #4f46e5)",
                      border: "none", color: saving || !keyInput.trim() ? "#475569" : "#fff",
                      fontSize: 12, fontWeight: 700, cursor: saving || !keyInput.trim() ? "not-allowed" : "pointer",
                      fontFamily: "inherit", display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                    }}
                  >
                    {saving
                      ? <><span style={{ width: 12, height: 12, border: "1.5px solid #475569", borderTopColor: "#a5b4fc", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />Kaydediliyor…</>
                      : "✓ Kaydet ve Etkinleştir"
                    }
                  </button>
                  <button
                    onClick={() => { setShowKeyForm(false); setKeyInput(""); setSaveResult(null); }}
                    style={{
                      padding: "9px 14px", borderRadius: 7, background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.08)", color: "#64748b",
                      fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                    }}
                  >
                    İptal
                  </button>
                </div>
                {saveResult && (
                  <div style={{
                    padding: "8px 10px", borderRadius: 6, fontSize: 11, fontFamily: "monospace",
                    background: saveResult.ok ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
                    color: saveResult.ok ? "#86efac" : "#fca5a5", lineHeight: 1.5,
                  }}>
                    {saveResult.ok ? `✓ ${saveResult.message}` : `✗ ${saveResult.error}`}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({ label, value, color, icon, delay }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.02)", border: `1px solid ${color}22`,
      borderRadius: 12, padding: "18px 22px", flex: 1, minWidth: 130,
      animation: `fadeSlideUp 0.5s ease ${delay}s both`,
    }}>
      <div style={{ fontSize: 13, color: "#8896a7", letterSpacing: "0.04em", marginBottom: 6 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 32, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>{value}</span>
        <span style={{ fontSize: 16, color: color + "88" }}>{icon}</span>
      </div>
    </div>
  );
}

// ── FindingCard ───────────────────────────────────────────────────────────────

function FindingCard({ finding, index }) {
  const [open, setOpen] = useState(false);
  const sev = SEV[finding.severity] ?? SEV.info;

  return (
    <div
      onClick={() => setOpen(!open)}
      style={{
        background: open ? sev.bg : "rgba(255,255,255,0.015)",
        border: `1px solid ${open ? sev.border : "rgba(255,255,255,0.06)"}`,
        borderRadius: 10, padding: "14px 18px", cursor: "pointer",
        transition: "all 0.2s ease",
        animation: `fadeSlideUp 0.4s ease ${0.04 * Math.min(index, 12)}s both`,
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = sev.border; e.currentTarget.style.background = sev.bg; }}
      onMouseLeave={e => { if (!open) { e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"; e.currentTarget.style.background = "rgba(255,255,255,0.015)"; }}}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 8,
          background: sev.bg, border: `1px solid ${sev.border}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, color: sev.color, fontWeight: 700, flexShrink: 0, marginTop: 1,
        }}>{sev.icon}</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>{finding.title}</span>
            <span style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 4,
              background: sev.bg, color: sev.color, fontWeight: 600,
              border: `1px solid ${sev.border}`, fontFamily: "monospace",
            }}>{finding.rule_code}</span>
            <span style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 4,
              background: "rgba(99,102,241,0.1)", color: "#818cf8",
              border: "1px solid rgba(99,102,241,0.2)", fontFamily: "monospace",
            }}>Katman {finding.layer}</span>
          </div>
          <p style={{ fontSize: 13, color: "#94a3b8", margin: "6px 0 0", lineHeight: 1.5 }}>
            {finding.description}
          </p>

          {open && (
            <div style={{
              marginTop: 14, paddingTop: 14,
              borderTop: "1px solid rgba(255,255,255,0.06)",
              display: "flex", flexDirection: "column", gap: 10,
            }}>
              {finding.found && (
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "#64748b", minWidth: 70 }}>Bulunan:</span>
                  <code style={{ fontSize: 12, color: "#f87171", background: "rgba(248,113,113,0.08)", padding: "2px 8px", borderRadius: 4, fontFamily: "'JetBrains Mono', monospace" }}>{finding.found}</code>
                </div>
              )}
              {finding.expected && (
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "#64748b", minWidth: 70 }}>Beklenen:</span>
                  <code style={{ fontSize: 12, color: "#4ade80", background: "rgba(74,222,128,0.08)", padding: "2px 8px", borderRadius: 4, fontFamily: "'JetBrains Mono', monospace" }}>{finding.expected}</code>
                </div>
              )}
              {finding.location?.text_snippet && (
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "#64748b", minWidth: 70 }}>Konum:</span>
                  <code style={{ fontSize: 11, color: "#94a3b8", background: "rgba(255,255,255,0.04)", padding: "2px 8px", borderRadius: 4, fontFamily: "'JetBrains Mono', monospace" }}>
                    {finding.location.section && `[${finding.location.section}] `}{finding.location.text_snippet}
                  </code>
                </div>
              )}
              {finding.reference && (
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "#64748b", minWidth: 70 }}>Referans:</span>
                  <span style={{ fontSize: 12, color: "#a78bfa" }}>{finding.reference}</span>
                </div>
              )}
              {finding.suggestion && (
                <div style={{ marginTop: 4, padding: "10px 14px", background: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.15)", borderRadius: 8, fontSize: 12, color: "#86efac", lineHeight: 1.5 }}>
                  💡 {finding.suggestion}
                </div>
              )}
              {finding.suggested_text && (
                <div style={{ marginTop: 2, padding: "12px 14px", background: "rgba(139,92,246,0.06)", border: "1px solid rgba(139,92,246,0.2)", borderRadius: 8, lineHeight: 1.6 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#a78bfa", letterSpacing: "0.06em", marginBottom: 6 }}>
                    ✦ YAPAY ZEKA YENİDEN YAZIM ÖNERİSİ
                  </div>
                  <div style={{ fontSize: 12, color: "#c4b5fd", fontStyle: "italic" }}>
                    "{finding.suggested_text}"
                  </div>
                </div>
              )}
              {finding.confidence < 1.0 && (
                <div style={{ fontSize: 11, color: "#64748b" }}>
                  Güven skoru: {Math.round(finding.confidence * 100)}%
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{ color: "#475569", fontSize: 16, transition: "transform 0.2s", transform: open ? "rotate(180deg)" : "rotate(0deg)", flexShrink: 0 }}>▾</div>
      </div>
    </div>
  );
}

// ── ErrorBanner ───────────────────────────────────────────────────────────────

function ErrorBanner({ message, onDismiss }) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 12,
      padding: "14px 16px", borderRadius: 10,
      background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.25)",
      animation: "fadeSlideUp 0.3s ease both",
    }}>
      <span style={{ color: "#f87171", fontSize: 16, flexShrink: 0, marginTop: 1 }}>✕</span>
      <div style={{ flex: 1, fontSize: 13, color: "#fca5a5", lineHeight: 1.55 }}>{message}</div>
      <button onClick={onDismiss} style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: 16, padding: 0, flexShrink: 0 }}>✕</button>
    </div>
  );
}

// ── Pipeline step definitions ─────────────────────────────────────────────────

const PIPELINE_STEPS = [
  { n: 1, label: "Belge ayrıştırılıyor",       desc: ".docx okuma · bölüm ve alan tespiti" },
  { n: 2, label: "Kural motoru çalışıyor",      desc: "Biçim · zorunlu alanlar · tutarlılık" },
  { n: 3, label: "Kılavuz veritabanı taranıyor", desc: "TDK vektör araması · RAG eşleştirme" },
  { n: 4, label: "Yapay zeka değerlendiriyor",  desc: "Semantik analiz · LLM bulgular · öneriler" },
  { n: 5, label: "Rapor hazırlanıyor",           desc: "Tüm bulgular derlendi" },
];

// Step timing (ms): how long to stay on each step before advancing
const STEP_DELAYS = [1400, 2200, 3500];   // step 1→2, 2→3, 3→4

// Download steps
const DOWNLOAD_STEPS = [
  { n: 1, label: "Belge yeniden analiz ediliyor",    desc: "Düzeltilecek konumlar belirleniyor" },
  { n: 2, label: "Hatalar otomatik düzeltiliyor",    desc: "Font · boşluk · yazım · kapanış" },
  { n: 3, label: "İndirme dosyası hazırlanıyor",     desc: "Düzeltilmiş .docx oluşturuluyor" },
];
const DOWNLOAD_STEP_DELAYS = [2000, 4000]; // 1→2, 2→3

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [file, setFile]               = useState(null);
  const [dragOver, setDragOver]       = useState(false);
  const [analyzing, setAnalyzing]     = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [results, setResults]         = useState(null);
  const [error, setError]             = useState(null);
  const [mode, setMode]               = useState("full");
  const [priority, setPriority]       = useState("all");
  const [currentStep, setCurrentStep]       = useState(0);  // 0=idle, 1-4=active, 5=done
  const [downloadStep, setDownloadStep]     = useState(0);  // 0=idle, 1-3=active
  const inputRef       = useRef(null);
  const abortRef       = useRef(null);
  const stepTimers     = useRef([]);
  const downloadTimers = useRef([]);

  const handleFile = useCallback((f) => {
    if (!f) return;
    if (!f.name.endsWith(".docx")) { setError("Sadece .docx dosyaları desteklenmektedir."); return; }
    if (f.size > 10 * 1024 * 1024) { setError("Dosya boyutu 10 MB sınırını aşıyor."); return; }
    setFile(f); setResults(null); setError(null);
  }, []);

  const handleDrop = useCallback((e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }, [handleFile]);

  const clearStepTimers = useCallback(() => {
    stepTimers.current.forEach(t => clearTimeout(t));
    stepTimers.current = [];
  }, []);

  const startAnalysis = useCallback(async () => {
    if (!file || analyzing) return;
    setAnalyzing(true); setError(null); setResults(null);

    // Kick off step animation
    setCurrentStep(1);
    clearStepTimers();
    let acc = 0;
    stepTimers.current = STEP_DELAYS.map((delay, i) => {
      acc += delay;
      return setTimeout(() => setCurrentStep(i + 2), acc);
    });

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const tid = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
    try {
      const data = await analyzeDocument(file, mode, controller.signal);
      clearStepTimers();
      setCurrentStep(5);
      setResults(data);
    } catch (err) {
      clearStepTimers();
      setCurrentStep(0);
      if (err.name === "AbortError" || err.message === "timeout") {
        setError(`İstek zaman aşımına uğradı (${REQUEST_TIMEOUT_MS / 1000}s). Backend çalışıyor mu?`);
      } else if (err.message?.includes("Failed to fetch") || err.message?.includes("NetworkError")) {
        setError(`Backend'e bağlanılamadı. ${API_BASE} adresinde uvicorn çalıştığından emin olun.`);
      } else {
        setError(err.message || "Bilinmeyen bir hata oluştu.");
      }
    } finally { clearTimeout(tid); setAnalyzing(false); }
  }, [file, mode, analyzing, clearStepTimers]);

  const cancelAnalysis = useCallback(() => {
    clearStepTimers();
    setCurrentStep(0);
    abortRef.current?.abort();
    setAnalyzing(false);
    setError(null);
  }, [clearStepTimers]);

  const clearDownloadTimers = useCallback(() => {
    downloadTimers.current.forEach(t => clearTimeout(t));
    downloadTimers.current = [];
  }, []);

  const downloadFixed = useCallback(async () => {
    if (!file || !results || downloading) return;
    setDownloading(true); setError(null);

    // Kick off download step animation
    setDownloadStep(1);
    clearDownloadTimers();
    let acc = 0;
    downloadTimers.current = DOWNLOAD_STEP_DELAYS.map((delay, i) => {
      acc += delay;
      return setTimeout(() => setDownloadStep(i + 2), acc);
    });

    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/analyze-and-fix?mode=${encodeURIComponent(mode)}`, { method: "POST", body: formData, signal: controller.signal });
      if (!res.ok) { let d = `HTTP ${res.status}`; try { const j = await res.json(); d = j.detail || d; } catch { } throw new Error(d); }
      const blob = await res.blob();
      clearDownloadTimers();
      setDownloadStep(0);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${file.name.replace(/\.docx$/i, "")}_duzeltilmis.docx`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      clearDownloadTimers();
      setDownloadStep(0);
      if (err.name === "AbortError" || err.message === "timeout") setError("İndirme zaman aşımına uğradı.");
      else if (err.message?.includes("Failed to fetch")) setError(`Backend'e bağlanılamadı.`);
      else setError(err.message || "İndirme sırasında hata oluştu.");
    } finally { clearTimeout(tid); setDownloading(false); }
  }, [file, mode, results, downloading, clearDownloadTimers]);

  const filteredFindings = (results?.findings ?? []).filter(f => priority === "all" || f.severity === priority);

  const pipelineSteps = PIPELINE_STEPS.map((s, i) => {
    let status = "pending";
    if (results) {
      status = "done";
    } else if (analyzing) {
      if (i + 1 < currentStep) status = "done";
      else if (i + 1 === currentStep) status = "active";
    }
    return { ...s, status };
  });

  return (
    <div style={{ minHeight: "100vh", background: "#0a0e17", color: "#e2e8f0", fontFamily: "'DM Sans', -apple-system, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
        @keyframes fadeSlideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
        @keyframes spin { to { transform: rotate(360deg); } }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
        button:hover:not(:disabled) { opacity: 0.9; }
      `}</style>

      {/* ── Header ── */}
      <header style={{
        borderBottom: "1px solid rgba(255,255,255,0.06)", padding: "16px 32px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "rgba(10,14,23,0.8)", backdropFilter: "blur(12px)",
        position: "sticky", top: 0, zIndex: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: "linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, fontWeight: 700, color: "#fff",
          }}>D</div>
          <div>
            <div style={{ fontSize: 11, color: "#64748b", letterSpacing: "0.08em", fontWeight: 500 }}>DEKANLIK / UYUM</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#f1f5f9", letterSpacing: "-0.01em" }}>Dekanlık Yazışma Uyum Denetleyicisi</div>
          </div>
        </div>
        <div style={{ padding: "5px 14px", borderRadius: 20, background: "rgba(6,182,212,0.1)", border: "1px solid rgba(6,182,212,0.2)", fontSize: 12, color: "#22d3ee", fontWeight: 600 }}>v0.6</div>
      </header>

      {/* ── Main Layout ── */}
      <div style={{
        display: "grid",
        gridTemplateColumns: results ? "420px 1fr" : "1fr",
        maxWidth: 1280, margin: "0 auto", padding: "32px 24px", gap: 32,
        transition: "grid-template-columns 0.3s ease",
      }}>

        {/* ── Left Panel ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

          {/* Sistem Durumu */}
          <SystemStatus />

          {/* Upload area */}
          <div
            style={{
              background: "rgba(255,255,255,0.02)",
              border: `2px dashed ${dragOver ? "#22d3ee" : "rgba(255,255,255,0.08)"}`,
              borderRadius: 16, padding: 32, transition: "all 0.2s ease", cursor: "pointer",
              ...(dragOver ? { background: "rgba(6,182,212,0.04)" } : {}),
            }}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
          >
            <input ref={inputRef} type="file" accept=".docx" style={{ display: "none" }} onChange={e => handleFile(e.target.files[0])} />
            <div style={{ textAlign: "center" }}>
              <div style={{
                width: 56, height: 56, borderRadius: 14, margin: "0 auto 16px",
                background: "rgba(6,182,212,0.08)", border: "1px solid rgba(6,182,212,0.15)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24,
              }}>📄</div>
              {file ? (
                <><div style={{ fontSize: 15, fontWeight: 600, color: "#e2e8f0" }}>{file.name}</div>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{(file.size / 1024).toFixed(1)} KB — Değiştirmek için tıklayın</div></>
              ) : (
                <><div style={{ fontSize: 15, fontWeight: 600, color: "#94a3b8" }}>Dosyayı seçin veya sürükleyip bırakın</div>
                <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>.docx biçiminde, en fazla 10 MB</div></>
              )}
            </div>
          </div>

          {/* Mode & Priority */}
          <div style={{ display: "flex", gap: 12 }}>
            {[
              { label: "MOD", value: mode, set: setMode, opts: [["full","Tam inceleme"],["format_only","Sadece biçim"],["content_only","Sadece içerik"]] },
              { label: "ÖNCELİK", value: priority, set: setPriority, opts: [["all","Tümü"],["error","Sadece hatalar"],["warning","Sadece uyarılar"],["info","Sadece bilgiler"]] },
            ].map(({ label, value, set, opts }) => (
              <div key={label} style={{ flex: 1 }}>
                <label style={{ fontSize: 11, color: "#64748b", display: "block", marginBottom: 6, fontWeight: 600, letterSpacing: "0.05em" }}>{label}</label>
                <select value={value} onChange={e => set(e.target.value)} disabled={analyzing} style={{
                  width: "100%", padding: "10px 14px", borderRadius: 10,
                  background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
                  color: "#e2e8f0", fontSize: 13, outline: "none", cursor: analyzing ? "not-allowed" : "pointer", fontFamily: "inherit",
                }}>
                  {opts.map(([v, l]) => <option key={v} value={v} style={{ background: "#1e293b" }}>{l}</option>)}
                </select>
              </div>
            ))}
          </div>

          {/* Analyze / Cancel */}
          {analyzing ? (
            <button onClick={cancelAnalysis} style={{
              padding: "14px 24px", borderRadius: 12, border: "1px solid rgba(239,68,68,0.3)",
              background: "rgba(239,68,68,0.06)", color: "#f87171",
              fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
            }}>
              <span style={{ width: 16, height: 16, border: "2px solid rgba(248,113,113,0.3)", borderTopColor: "#f87171", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />
              İnceleniyor… (İptal et)
            </button>
          ) : (
            <button onClick={startAnalysis} disabled={!file} style={{
              padding: "14px 24px", borderRadius: 12, border: "none",
              background: file ? "linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)" : "rgba(255,255,255,0.05)",
              color: file ? "#fff" : "#475569", fontSize: 14, fontWeight: 700,
              cursor: file ? "pointer" : "not-allowed", fontFamily: "inherit", transition: "all 0.2s ease",
            }}>
              İncelemeyi Başlat
            </button>
          )}

          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

          {/* Pipeline */}
          <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 12, padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#94a3b8", marginBottom: 14, letterSpacing: "0.03em" }}>İşlem Hattı</div>

            {/* Active step banner */}
            {analyzing && currentStep >= 1 && currentStep <= 4 && (() => {
              const step = PIPELINE_STEPS[currentStep - 1];
              const isLlm = currentStep === 4;
              return (
                <div style={{
                  marginBottom: 14, padding: "10px 14px", borderRadius: 8,
                  background: isLlm ? "rgba(251,146,60,0.07)" : "rgba(6,182,212,0.06)",
                  border: `1px solid ${isLlm ? "rgba(251,146,60,0.25)" : "rgba(6,182,212,0.2)"}`,
                  display: "flex", alignItems: "center", gap: 10,
                }}>
                  <span style={{
                    width: 14, height: 14, flexShrink: 0,
                    border: `2px solid ${isLlm ? "rgba(251,146,60,0.3)" : "rgba(6,182,212,0.3)"}`,
                    borderTopColor: isLlm ? "#fb923c" : "#22d3ee",
                    borderRadius: "50%", display: "inline-block",
                    animation: "spin 0.9s linear infinite",
                  }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: isLlm ? "#fb923c" : "#22d3ee" }}>
                      {step.label}…
                    </div>
                    <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                      {isLlm ? "Bu adım 20–40 saniye sürebilir" : step.desc}
                    </div>
                  </div>
                </div>
              );
            })()}

            {pipelineSteps.map((step, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                padding: "7px 0",
                opacity: step.status === "pending" ? 0.35 : 1,
                transition: "opacity 0.3s ease",
              }}>
                <div style={{
                  width: 22, height: 22, borderRadius: 6, fontSize: 11, fontWeight: 700,
                  flexShrink: 0, marginTop: 1,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: step.status === "done"   ? "rgba(34,197,94,0.15)"
                             : step.status === "active" ? "rgba(6,182,212,0.15)"
                             : "rgba(255,255,255,0.05)",
                  color:      step.status === "done"   ? "#4ade80"
                             : step.status === "active" ? "#22d3ee"
                             : "#475569",
                  border: `1px solid ${step.status === "done"   ? "rgba(34,197,94,0.3)"
                                      : step.status === "active" ? "rgba(6,182,212,0.3)"
                                      : "rgba(255,255,255,0.08)"}`,
                  ...(step.status === "active" ? { animation: "pulse 1.5s ease infinite" } : {}),
                }}>
                  {step.status === "done" ? "✓" : step.n}
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: step.status === "done" ? "#94a3b8" : step.status === "active" ? "#e2e8f0" : "#64748b" }}>
                    {step.label}
                  </div>
                  <div style={{ fontSize: 11, color: "#475569", marginTop: 1 }}>{step.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Right Panel: Results ── */}
        {results ? (
          <div style={{ animation: "fadeSlideUp 0.5s ease both" }}>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 16, fontFamily: "'JetBrains Mono', monospace" }}>
              📄 {results.filename}
            </div>

            {/* Download button + inline progress */}
            <div style={{ marginBottom: 24 }}>
              <button onClick={downloadFixed} disabled={downloading} style={{
                display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
                width: "100%", padding: "13px 20px", borderRadius: downloading ? "10px 10px 0 0" : 10, border: "none",
                background: downloading ? "rgba(34,197,94,0.06)" : "linear-gradient(135deg, #22c55e 0%, #15803d 100%)",
                color: downloading ? "#4ade80" : "#fff", fontSize: 14, fontWeight: 700,
                cursor: downloading ? "not-allowed" : "pointer", fontFamily: "inherit",
                boxShadow: downloading ? "none" : "0 4px 14px rgba(34,197,94,0.25)",
                borderBottom: downloading ? "none" : undefined,
                transition: "all 0.2s",
              }}>
                {downloading ? (
                  <><span style={{ width: 16, height: 16, border: "2px solid rgba(74,222,128,0.3)", borderTopColor: "#4ade80", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />
                  {downloadStep >= 1 ? DOWNLOAD_STEPS[downloadStep - 1]?.label ?? "İndiriliyor…" : "Hazırlanıyor…"}…</>
                ) : (<><span style={{ fontSize: 18 }}>↓</span> Düzeltilmiş Belgeyi İndir</>)}
              </button>

              {/* Download step progress panel */}
              {downloading && (
                <div style={{
                  border: "1px solid rgba(34,197,94,0.2)", borderTop: "none",
                  borderRadius: "0 0 10px 10px",
                  background: "rgba(34,197,94,0.03)", padding: "10px 14px",
                  display: "flex", flexDirection: "column", gap: 6,
                }}>
                  {DOWNLOAD_STEPS.map((s, i) => {
                    const stepNum = i + 1;
                    const isDone = downloadStep > stepNum;
                    const isActive = downloadStep === stepNum;
                    return (
                      <div key={i} style={{
                        display: "flex", alignItems: "center", gap: 8,
                        opacity: !isDone && !isActive ? 0.3 : 1,
                        transition: "opacity 0.3s ease",
                      }}>
                        <div style={{
                          width: 18, height: 18, borderRadius: 5, flexShrink: 0,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 10, fontWeight: 700,
                          background: isDone ? "rgba(34,197,94,0.15)" : isActive ? "rgba(34,197,94,0.12)" : "rgba(255,255,255,0.04)",
                          color: isDone ? "#4ade80" : isActive ? "#22c55e" : "#475569",
                          border: `1px solid ${isDone ? "rgba(34,197,94,0.3)" : isActive ? "rgba(34,197,94,0.25)" : "rgba(255,255,255,0.06)"}`,
                          ...(isActive ? { animation: "pulse 1.5s ease infinite" } : {}),
                        }}>
                          {isDone ? "✓" : s.n}
                        </div>
                        <div>
                          <div style={{ fontSize: 11, fontWeight: 600, color: isDone ? "#64748b" : isActive ? "#86efac" : "#475569" }}>
                            {s.label}
                          </div>
                          <div style={{ fontSize: 10, color: "#334155" }}>{s.desc}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Stats */}
            <div style={{ display: "flex", gap: 14, marginBottom: 24, flexWrap: "wrap" }}>
              <StatCard
                label="Uyum Skoru"
                value={`${results.compliance_score}/100`}
                color={results.compliance_score >= 80 ? "#22c55e" : results.compliance_score >= 60 ? "#f59e0b" : "#ef4444"}
                icon="★"
                delay={0.05}
              />
              <StatCard label="Toplam Bulgu" value={results.total_findings} color="#e2e8f0" icon="◈" delay={0.1} />
              <StatCard label="Hata"         value={results.errors}         color="#ef4444" icon="✕" delay={0.2} />
              <StatCard label="Uyarı"        value={results.warnings}       color="#f59e0b" icon="△" delay={0.3} />
              <StatCard label="Bilgi"        value={results.infos}          color="#06b6d4" icon="○" delay={0.4} />
            </div>

            {/* Layer breakdown */}
            <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap", animation: "fadeSlideUp 0.5s ease 0.3s both" }}>
              {["A","B","C"].map(layer => {
                const count = filteredFindings.filter(f => f.layer === layer).length;
                return (
                  <div key={layer} style={{
                    padding: "6px 14px", borderRadius: 8,
                    background: count > 0 ? "rgba(99,102,241,0.08)" : "rgba(255,255,255,0.02)",
                    border: `1px solid ${count > 0 ? "rgba(99,102,241,0.2)" : "rgba(255,255,255,0.06)"}`,
                    fontSize: 12, color: count > 0 ? "#a5b4fc" : "#475569",
                  }}>
                    <span style={{ fontWeight: 700 }}>Katman {layer}</span>
                    <span style={{ marginLeft: 6, opacity: 0.7 }}>{LAYER_LABELS[layer]}</span>
                    <span style={{ marginLeft: 8, padding: "1px 6px", borderRadius: 4, background: count > 0 ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.05)", fontWeight: 700, fontFamily: "monospace" }}>{count}</span>
                  </div>
                );
              })}
            </div>

            {/* Findings */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {filteredFindings.length === 0 ? (
                <div style={{ textAlign: "center", padding: 48, color: "#475569", fontSize: 14 }}>
                  {results.total_findings === 0 ? "🎉 Belge uyum kontrolünden geçti." : "Bu filtrede bulgu yok."}
                </div>
              ) : filteredFindings.map((f, i) => <FindingCard key={f.id} finding={f} index={i} />)}
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300, color: "#334155" }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>📋</div>
              <div style={{ fontSize: 15, color: "#475569" }}>Henüz dosya yüklenmedi</div>
              <div style={{ fontSize: 13, color: "#334155", marginTop: 4 }}>Sol taraftan bir belge yükleyerek başlayın</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
