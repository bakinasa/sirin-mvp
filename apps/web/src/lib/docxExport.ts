import { api } from "./api";

type ExportJob = {
  id: string;
  export_type: string;
  status: string;
  result_content: unknown;
  error_message: string;
};

export function downloadDocx(content: unknown, fallbackFilename: string) {
  const c = content as Record<string, string> | null;
  if (!c?.docx_base64) return;
  const binary = atob(c.docx_base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = c.filename || fallbackFilename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function exportDocx(
  projectId: string,
  exportType: "docx_scenario" | "docx_profession_map",
  fallbackFilename: string
): Promise<ExportJob> {
  const created = await api<ExportJob>(`/projects/${projectId}/exports`, {
    method: "POST",
    body: JSON.stringify({ export_type: exportType }),
  });
  const full = await api<ExportJob>(`/exports/${created.id}`);
  if (full.status === "ready") {
    downloadDocx(full.result_content, fallbackFilename);
  }
  return full;
}
