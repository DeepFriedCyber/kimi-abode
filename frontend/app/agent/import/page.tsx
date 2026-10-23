"use client";

/**
 * Agent listing import — upload a file or paste an email, preview, then commit.
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  importListingText,
  importListingsFile,
  importTemplateUrl,
  type ImportReport,
} from "../../../lib/listings-api";
import { formatPrice, formatStatus, formatType } from "../../../lib/format";
import { ApiError } from "../../../lib/api";

const ACCEPTED = ".csv,.tsv,.xlsx,.json,.jsonl,.xml,.txt";
const MAX_BYTES = 8 * 1024 * 1024;

type Mode = "file" | "text";

export default function AgentImportPage() {
  const [mode, setMode] = useState<Mode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [agentId, setAgentId] = useState("");
  const [mappingText, setMappingText] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState<"preview" | "commit" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setApiKey(sessionStorage.getItem("abode.apiKey") ?? "");
    setAgentId(sessionStorage.getItem("abode.agentId") ?? "");
  }, []);

  const remember = (key: string, value: string) => {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  };

  const parseMapping = (): Record<string, string> | undefined => {
    if (!mappingText.trim()) return undefined;
    const parsed = JSON.parse(mappingText) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("Mapping must be a JSON object, e.g. {\"address\": \"Property Address\"}");
    }
    return parsed as Record<string, string>;
  };

  const run = async (dryRun: boolean) => {
    setError(null);
    setBusy(dryRun ? "preview" : "commit");

    try {
      const options = { dryRun, apiKey, agentId, mapping: parseMapping() };
      const result =
        mode === "file"
          ? await importListingsFile(requireFile(file), options)
          : await importListingText(text, options);
      setReport(result);
    } catch (err) {
      setReport(null);
      if (err instanceof ApiError) setError(err.message);
      else if (err instanceof Error) setError(err.message);
      else setError("Import failed");
    } finally {
      setBusy(null);
    }
  };

  const canRun = mode === "file" ? Boolean(file) : text.trim().length > 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold">Import listings</h1>
        <p className="text-gray-600">
          Upload whatever your CRM exports, or paste an email. We detect the
          columns, normalise the values, and show you exactly what will be
          imported before anything is saved.
        </p>
        <p className="text-sm text-gray-500">
          Templates:{" "}
          <a className="text-blue-600 hover:underline" href={importTemplateUrl("csv")} download>
            CSV
          </a>{" "}
          ·{" "}
          <a className="text-blue-600 hover:underline" href={importTemplateUrl("xlsx")} download>
            Excel
          </a>
          {" · "}
          Accepts CSV, TSV, XLSX, JSON, JSONL, XML (BLM/RESO) and TXT · max 8 MB
        </p>
      </header>

      <section className="bg-white border rounded-xl p-4 space-y-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">API key (optional in dev)</span>
            <input
              type="password"
              value={apiKey}
              onChange={(event) => {
                setApiKey(event.target.value);
                remember("abode.apiKey", event.target.value);
              }}
              placeholder="X-API-Key"
              className="w-full border rounded-lg px-3 py-2"
              autoComplete="off"
            />
          </label>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">Agent / branch id</span>
            <input
              type="text"
              value={agentId}
              onChange={(event) => {
                setAgentId(event.target.value);
                remember("abode.agentId", event.target.value);
              }}
              placeholder="e.g. acme-sandbach"
              className="w-full border rounded-lg px-3 py-2"
            />
          </label>
        </div>
        <p className="text-xs text-gray-500">
          Stored in this browser session only. Listings are attributed to the
          agent id and re-uploads update rather than duplicate.
        </p>
      </section>

      <div className="flex gap-2">
        {(["file", "text"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => {
              setMode(value);
              setReport(null);
              setError(null);
            }}
            className={`px-4 py-2 rounded-full text-sm font-medium border ${
              mode === value
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-gray-700 border-gray-300 hover:border-gray-400"
            }`}
          >
            {value === "file" ? "Upload a file" : "Paste a listing"}
          </button>
        ))}
      </div>

      {mode === "file" ? (
        <section
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const dropped = event.dataTransfer.files?.[0];
            if (dropped) selectFile(dropped);
          }}
          className={`bg-white border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
            dragging ? "border-blue-500 bg-blue-50" : "border-gray-300"
          }`}
        >
          <p className="text-gray-700 font-medium">
            {file ? file.name : "Drag a file here, or choose one"}
          </p>
          {file && (
            <p className="text-xs text-gray-500 mt-1">
              {(file.size / 1024).toFixed(0)} KB · {file.type || "unknown type"}
            </p>
          )}
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              if (chosen) selectFile(chosen);
            }}
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            className="mt-4 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800"
          >
            Choose file
          </button>
        </section>
      ) : (
        <section className="bg-white border rounded-xl p-4">
          <label htmlFor="paste" className="block text-sm text-gray-600 mb-1">
            Paste an email or property description
          </label>
          <textarea
            id="paste"
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={10}
            maxLength={20_000}
            placeholder={
              "Stunning 4 bed detached house in Sandbach, CW11 1JD\nGuide price £375,000. Large garden and garage."
            }
            className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
          />
          <p className="text-xs text-gray-500 mt-1">
            We extract the address, postcode, price, bedrooms and property type,
            then let you check the result before saving.
          </p>
        </section>
      )}

      <details className="bg-white border rounded-xl p-4">
        <summary className="cursor-pointer text-sm font-medium">
          Advanced: override column mapping
        </summary>
        <p className="text-xs text-gray-500 mt-2">
          Only needed when auto-detection guesses wrong. JSON object mapping our
          fields to your column names, e.g.{" "}
          <code className="bg-gray-100 px-1 rounded">
            {`{"address": "Property", "price": "Asking"}`}
          </code>
          .
        </p>
        <textarea
          value={mappingText}
          onChange={(event) => setMappingText(event.target.value)}
          rows={3}
          placeholder='{"address": "Property Address", "price": "Guide Price"}'
          className="mt-2 w-full border rounded-lg px-3 py-2 font-mono text-xs"
        />
      </details>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={!canRun || busy !== null}
          onClick={() => void run(true)}
          className="px-5 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {busy === "preview" ? "Checking…" : "Preview import"}
        </button>
        <button
          type="button"
          disabled={!canRun || busy !== null}
          onClick={() => void run(false)}
          className="px-5 py-2.5 bg-green-700 text-white rounded-lg font-medium hover:bg-green-800 disabled:opacity-50"
        >
          {busy === "commit" ? "Importing…" : "Import now"}
        </button>
        <span className="text-sm text-gray-500 self-center">
          Preview writes nothing. Import is idempotent — re-running updates the same listings.
        </span>
      </div>

      {error && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
          {error}
        </div>
      )}

      {report && <ReportView report={report} />}
    </div>
  );

  function selectFile(chosen: File) {
    if (chosen.size > MAX_BYTES) {
      setError(`“${chosen.name}” is larger than 8 MB`);
      return;
    }
    setError(null);
    setFile(chosen);
    setReport(null);
  }
}

function requireFile(file: File | null): File {
  if (!file) throw new Error("Choose a file first");
  return file;
}

function ReportView({ report }: { report: ImportReport }) {
  const stats = [
    ["Rows found", report.received],
    ["Ready", report.valid],
    ["Invalid", report.invalid],
    ["Duplicates", report.duplicates],
    [report.dry_run ? "Would import" : "Imported", report.dry_run ? report.valid : report.imported],
  ] as const;

  const first = report.preview[0];

  return (
    <section className="space-y-4" aria-live="polite">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">
          {report.dry_run ? "Preview" : "Import complete"}
        </h2>
        <span className="text-xs px-2 py-1 bg-gray-100 rounded-full uppercase tracking-wide">
          {report.format}
          {report.delimiter ? ` · “${report.delimiter}”` : ""}
        </span>
        {report.geocoded > 0 && (
          <span className="text-xs text-gray-500">{report.geocoded} geocoded</span>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {stats.map(([label, value]) => (
          <div key={label} className="bg-white border rounded-xl p-3 text-center">
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-xs text-gray-500">{label}</p>
          </div>
        ))}
      </div>

      {!report.dry_run && report.imported > 0 && (
        <div className="p-4 bg-green-50 border border-green-200 rounded-lg text-green-900 text-sm">
          {report.imported} {report.imported === 1 ? "listing" : "listings"} saved and
          searchable.{" "}
          {first && (
            <Link
              className="underline"
              href={`/search?q=${encodeURIComponent(first.address_line1)}`}
            >
              View in search →
            </Link>
          )}
          {" · "}
          <Link className="underline" href="/agent/listings">
            Manage photos →
          </Link>
        </div>
      )}

      {Object.keys(report.columns).length > 0 && (
        <div className="bg-white border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-2">Detected columns</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(report.columns).map(([canonical, source]) => (
              <span
                key={canonical}
                className="text-xs px-2 py-1 rounded-full bg-blue-50 text-blue-800"
                title={`confidence ${(report.confidence[canonical] ?? 0).toFixed(1)}`}
              >
                {canonical} ← {source}
              </span>
            ))}
            {report.unmapped_columns.map((column) => (
              <span
                key={column}
                className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-500"
                title="Not mapped — ignored"
              >
                {column}
              </span>
            ))}
          </div>
        </div>
      )}

      {report.errors.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-red-900 mb-2">
            {report.errors.length} row {report.errors.length === 1 ? "error" : "errors"}
          </h3>
          <ul className="text-sm text-red-800 space-y-1 max-h-48 overflow-auto">
            {report.errors.map((issue, index) => (
              <li key={index}>
                Row {issue.row}: {issue.message}
                {issue.field ? ` (${issue.field})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.warnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-amber-900 mb-2">Warnings</h3>
          <ul className="text-sm text-amber-800 space-y-1 max-h-40 overflow-auto">
            {report.warnings.slice(0, 20).map((issue, index) => (
              <li key={index}>
                {issue.row ? `Row ${issue.row}: ` : ""}
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.preview.length > 0 && (
        <div className="bg-white border rounded-xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-3 py-2">Row</th>
                <th className="px-3 py-2">Address</th>
                <th className="px-3 py-2">Postcode</th>
                <th className="px-3 py-2">Price</th>
                <th className="px-3 py-2">Beds</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {report.preview.map((item, index) => (
                <tr key={`${item.address_line1}-${index}`} className="border-t">
                  <td className="px-3 py-2 text-gray-500">
                    {(item as { source_row?: number }).source_row ?? index + 2}
                  </td>
                  <td className="px-3 py-2">{item.address_line1}</td>
                  <td className="px-3 py-2">{item.postcode ?? "—"}</td>
                  <td className="px-3 py-2">
                    {formatPrice(item.asking_price ?? item.price_paid)}
                  </td>
                  <td className="px-3 py-2">{item.num_beds ?? "—"}</td>
                  <td className="px-3 py-2 capitalize">{formatType(item.property_type)}</td>
                  <td className="px-3 py-2 capitalize">
                    {formatStatus(item.listing_status ?? "sold")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-gray-500 px-3 py-2">
            Showing {report.preview.length} of {report.valid} ready rows.
          </p>
        </div>
      )}
    </section>
  );
}
