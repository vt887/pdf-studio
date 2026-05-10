import { useEffect, useState } from "react";
import type { FormEvent } from "react";

type DocumentSummary = {
  document_id: string;
  source_filename: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  latest_job_id: string | null;
  latest_job_status: string | null;
  has_model: boolean;
  has_pdf: boolean;
};

type JobStatus = {
  id: string;
  status: string;
  error_message: string | null;
};

function fmtDate(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function App() {
  const apiBase = (import.meta as { env: { VITE_API_BASE_URL?: string } }).env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  const [modelText, setModelText] = useState<string>("");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string>("Upload a file to start stub processing.");
  const [loading, setLoading] = useState(false);

  async function refreshDocuments() {
    const response = await fetch(`${apiBase}/v1/documents`);
    if (!response.ok) return;
    const data = (await response.json()) as DocumentSummary[];
    setDocuments(data);
    if (!activeDocumentId && data.length > 0) {
      setActiveDocumentId(data[0].document_id);
    }
  }

  useEffect(() => {
    void refreshDocuments();
    const timer = window.setInterval(() => {
      void refreshDocuments();
    }, 3000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "running")) return;
    const timer = window.setInterval(async () => {
      const response = await fetch(`${apiBase}/v1/jobs/${job.id}`);
      if (!response.ok) return;
      const next = (await response.json()) as JobStatus;
      setJob(next);
      if (next.status !== "queued" && next.status !== "running") {
        void refreshDocuments();
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("file") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) {
      setUploadMessage("Choose a file first.");
      return;
    }

    setLoading(true);
    setUploadMessage("Uploading...");
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(`${apiBase}/v1/documents`, { method: "POST", body });
    if (!response.ok) {
      setLoading(false);
      setUploadMessage(`Upload failed: ${response.status}`);
      return;
    }
    const data = (await response.json()) as { document_id: string; job_id: string };
    setJob({ id: data.job_id, status: "queued", error_message: null });
    setActiveDocumentId(data.document_id);
    setUploadMessage(`Queued document ${data.document_id}. Job ${data.job_id}`);
    input.value = "";
    setLoading(false);
    void refreshDocuments();
  }

  async function loadModel(documentId: string) {
    const response = await fetch(`${apiBase}/v1/documents/${documentId}/model`);
    if (response.status === 409) {
      const body = (await response.json()) as { detail?: string };
      setModelText(body.detail ?? "Model is not ready.");
      return;
    }
    if (!response.ok) {
      setModelText(`Failed to load model (${response.status})`);
      return;
    }
    const data = await response.json();
    setModelText(JSON.stringify(data, null, 2));
  }

  const active = documents.find((doc) => doc.document_id === activeDocumentId) ?? null;
  const pdfUrl = active ? `${apiBase}/v1/documents/${active.document_id}/pdf` : null;

  return (
    <main className="app">
      <section className="panel">
        <p className="eyebrow">pdf-studio</p>
        <h1>Review UI</h1>
        <form onSubmit={onSubmit} className="form">
          <input name="file" type="file" accept="image/*,.pdf,.tif,.tiff,.jpg,.jpeg,.png" />
          <button type="submit" disabled={loading}>{loading ? "Uploading..." : "Upload"}</button>
        </form>
        <p className="lede">{uploadMessage}</p>
        {job ? (
          <p className={`job job-${job.status}`}>
            Job `{job.id}`: {job.status}
            {job.error_message ? ` - ${job.error_message}` : ""}
          </p>
        ) : null}
      </section>

      <section className="panel">
        <h2>Documents</h2>
        <div className="table">
          {documents.map((doc) => (
            <button key={doc.document_id} className={`row ${activeDocumentId === doc.document_id ? "active" : ""}`} onClick={() => setActiveDocumentId(doc.document_id)}>
              <span>{doc.source_filename}</span>
              <span>{doc.status}</span>
              <span>{doc.latest_job_status ?? "-"}</span>
              <span>{fmtDate(doc.created_at)}</span>
            </button>
          ))}
          {documents.length === 0 ? <p>No documents yet.</p> : null}
        </div>
      </section>

      {active ? (
        <>
          <section className="panel">
            <h2>Document {active.document_id}</h2>
            <p>Status: {active.status}</p>
            <p>Latest job: {active.latest_job_status ?? "-"}</p>
            <div className="actions">
              <button onClick={() => void loadModel(active.document_id)}>Load model JSON</button>
              <a href={`${apiBase}/v1/documents/${active.document_id}/model`} target="_blank" rel="noreferrer">Open model</a>
              {active.has_pdf ? <a href={pdfUrl ?? "#"} target="_blank" rel="noreferrer">Open PDF</a> : <span>PDF processing</span>}
            </div>
          </section>

          <section className="panel">
            <h2>PDF Preview</h2>
            {active.has_pdf && pdfUrl ? (
              <iframe title="pdf-preview" src={pdfUrl} className="pdf" />
            ) : (
              <p>PDF is processing...</p>
            )}
          </section>

          <section className="panel">
            <details>
              <summary>Model JSON</summary>
              <pre className="json">{modelText || "Load model to inspect reconstruction JSON."}</pre>
            </details>
          </section>
        </>
      ) : null}
    </main>
  );
}
