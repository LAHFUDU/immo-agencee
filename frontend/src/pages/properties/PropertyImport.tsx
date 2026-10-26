import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { BackLink } from "../../components/Layout";
import { Alert, Button, Card, Checkbox, PageHeader, StatCard, useToast } from "../../components/ui";
import { api, download } from "../../lib/api";

interface Report {
  total_rows: number;
  valid_rows: number;
  imported: number;
  imported_references: string[];
  error_rows: number;
  errors: { row: number; field: string; message: string }[];
  duplicates: { row: number; reason: string }[];
  dry_run: boolean;
}

function errorsCsv(r: Report): string {
  const esc = (s: string | number) => `"${String(s).replace(/"/g, '""')}"`;
  const lines = [["ligne", "champ", "erreur"].join(";")];
  r.errors.forEach((e) => lines.push([e.row, e.field, e.message].map(esc).join(";")));
  r.duplicates.forEach((d) => lines.push([d.row, "doublon", d.reason].map(esc).join(";")));
  return "﻿" + lines.join("\n");
}

export default function PropertyImport() {
  const toast = useToast();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [allowDup, setAllowDup] = useState(false);
  const [report, setReport] = useState<Report | null>(null);

  const run = useMutation({
    mutationFn: (dryRun: boolean) => {
      const fd = new FormData();
      fd.append("file", file!);
      fd.append("dry_run", String(dryRun));
      fd.append("allow_duplicates", String(allowDup));
      return api<Report>("/properties/import", { form: fd });
    },
    onSuccess: (r) => {
      setReport(r);
      if (!r.dry_run) {
        qc.invalidateQueries({ queryKey: ["properties"] });
        toast.success(`${r.imported} bien(s) importé(s). Le moteur de correspondance a été exécuté pour chacun.`);
      }
    },
    onError: toast.error,
  });

  const saveErrors = () => {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([errorsCsv(report)], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "rapport_erreurs_import.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <PageHeader back={<BackLink to="/app/properties">Biens</BackLink>} title="Import de biens (CSV / Excel)" subtitle="Le fichier est d'abord analysé sans rien enregistrer ; vous confirmez ensuite l'import des lignes valides." />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="1. Préparer le fichier">
          <ul className="mb-4 list-disc space-y-1 pl-5 text-sm text-slate-600">
            <li>Formats acceptés : .csv (séparateur ; ou ,) et .xlsx</li>
            <li>Colonnes obligatoires : type, transaction, titre, ville, prix</li>
            <li>Types et équipements : code ou libellé (ex. « Appartement », « Parking »)</li>
            <li>Transaction : vente ou location</li>
          </ul>
          <Button variant="secondary" icon={<Download className="h-4 w-4" />} onClick={() => download("/properties/import/template").catch(toast.error)}>
            Télécharger le modèle
          </Button>
        </Card>
        <Card title="2. Analyser" className="lg:col-span-2">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <input
              ref={input}
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              hidden
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setReport(null);
              }}
            />
            <Button variant="secondary" icon={<FileSpreadsheet className="h-4 w-4" />} onClick={() => input.current?.click()}>
              {file ? file.name : "Choisir un fichier"}
            </Button>
            <Checkbox label="Importer aussi les doublons probables" checked={allowDup} onChange={setAllowDup} />
            <Button disabled={!file} loading={run.isPending && run.variables === true} onClick={() => run.mutate(true)}>
              Analyser
            </Button>
          </div>
        </Card>
      </div>

      {report && (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-4">
            <StatCard label="Lignes lues" value={report.total_rows} />
            <StatCard label="Lignes valides" value={report.valid_rows} tone="green" />
            <StatCard label="Lignes en erreur" value={report.error_rows} tone={report.error_rows ? "red" : "slate"} />
            <StatCard label="Doublons détectés" value={report.duplicates.length} tone={report.duplicates.length ? "gold" : "slate"} />
          </div>
          {report.dry_run ? (
            <Card
              title="3. Confirmer"
              actions={
                (report.errors.length > 0 || report.duplicates.length > 0) && (
                  <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={saveErrors}>
                    Rapport d'erreurs (CSV)
                  </Button>
                )
              }
            >
              {report.valid_rows ? (
                <div className="flex flex-wrap items-center gap-3">
                  <p className="text-sm text-slate-600">
                    {report.valid_rows} bien(s) seront créés{report.error_rows ? ` ; ${report.error_rows} ligne(s) en erreur seront ignorées` : ""}.
                  </p>
                  <Button icon={<Upload className="h-4 w-4" />} loading={run.isPending && run.variables === false} onClick={() => run.mutate(false)}>
                    Importer {report.valid_rows} bien(s)
                  </Button>
                </div>
              ) : (
                <Alert color="red">Aucune ligne valide à importer. Corrigez le fichier puis relancez l'analyse.</Alert>
              )}
            </Card>
          ) : (
            <Alert color="green" title="Import terminé">
              {report.imported} bien(s) créé(s) : {report.imported_references.slice(0, 20).join(", ")}
              {report.imported_references.length > 20 ? "…" : ""}. <Link to="/app/properties" className="underline">Voir l'inventaire</Link>
            </Alert>
          )}
          {(report.errors.length > 0 || report.duplicates.length > 0) && (
            <Card title="Détail des anomalies">
              <div className="scrollbar-thin max-h-[420px] overflow-auto">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 bg-white">
                    <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-3 py-2">Ligne</th>
                      <th className="px-3 py-2">Champ</th>
                      <th className="px-3 py-2">Problème</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {report.errors.map((e, i) => (
                      <tr key={`e${i}`}>
                        <td className="px-3 py-1.5">{e.row}</td>
                        <td className="px-3 py-1.5 font-mono text-xs">{e.field}</td>
                        <td className="px-3 py-1.5 text-red-700">{e.message}</td>
                      </tr>
                    ))}
                    {report.duplicates.map((d, i) => (
                      <tr key={`d${i}`}>
                        <td className="px-3 py-1.5">{d.row}</td>
                        <td className="px-3 py-1.5 font-mono text-xs">doublon</td>
                        <td className="px-3 py-1.5 text-amber-700">{d.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </>
  );
}
