type QrOrderUrlOptions = {
  branchId: string;
  tableId: string;
  currentOrigin: string;
  publicAppUrl?: string;
};

function normalizedBaseUrl(publicAppUrl: string | undefined, currentOrigin: string) {
  const configured = (publicAppUrl || "").trim().replace(/\/+$/, "");
  return configured || currentOrigin.replace(/\/+$/, "");
}

export function qrOrderUrl({ branchId, tableId, currentOrigin, publicAppUrl }: QrOrderUrlOptions) {
  const baseUrl = normalizedBaseUrl(publicAppUrl, currentOrigin);
  return `${baseUrl}/qr-order?branch_id=${encodeURIComponent(branchId)}&table_id=${encodeURIComponent(tableId)}`;
}
