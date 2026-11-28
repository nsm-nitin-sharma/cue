import { formatINR, formatShortOp } from "@/lib/format";
import type { ReceiptSlip, Sale } from "@/types/cue";

function escHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function triggerPrintableHtml(html: string, title: string): void {
  if (typeof window === "undefined") return;
  const popup = window.open("", "_blank", "width=760,height=900");
  if (popup) {
    popup.document.open();
    popup.document.write(html);
    popup.document.close();
    popup.document.title = title;
    popup.focus();
    setTimeout(() => {
      try {
        popup.print();
      } catch {
        // user closed popup
      }
    }, 180);
    return;
  }

  // Fallback hidden iframe if popup blocker prevents window.open
  const frame = document.createElement("iframe");
  frame.style.position = "fixed";
  frame.style.right = "0";
  frame.style.bottom = "0";
  frame.style.width = "0";
  frame.style.height = "0";
  frame.style.border = "0";
  document.body.appendChild(frame);
  const doc = frame.contentWindow?.document;
  if (!doc) {
    document.body.removeChild(frame);
    return;
  }
  doc.open();
  doc.write(html);
  doc.close();
  setTimeout(() => {
    try {
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    } finally {
      setTimeout(() => document.body.removeChild(frame), 1500);
    }
  }, 180);
}

function buildBillShell(opts: {
  storeName: string;
  storeCity?: string;
  docTitle: string;
  invoiceNo: string;
  dateStr: string;
  customerLabel: string;
  paymentBadge: string;
  rowsHtml: string;
  totalAmount?: number;
  paidAmount?: number;
  balanceDue?: number;
  footerNote: string;
}): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>${escHtml(opts.docTitle)}</title>
<style>
  @page { size: A4; margin: 16mm; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #15171A;
    background: #FFFFFF;
    margin: 0;
    padding: 24px;
    line-height: 1.45;
  }
  .sheet {
    max-width: 640px;
    margin: 0 auto;
    border: 1px solid #E2E0DB;
    border-radius: 14px;
    padding: 28px;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 2px solid #15171A;
    padding-bottom: 16px;
    margin-bottom: 18px;
  }
  .brand { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; margin: 0; }
  .city { font-size: 12px; color: #5C6370; margin: 2px 0 0; }
  .meta { text-align: right; font-size: 12px; color: #5C6370; font-family: ui-monospace, monospace; }
  .badge {
    display: inline-block;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    background: #F4F2ED;
    color: #15171A;
    border: 1px solid #DDD8CE;
  }
  .party {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    font-size: 13px;
  }
  table { width: 100%; border-collapse: collapse; margin-bottom: 18px; }
  th {
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #5C6370;
    border-bottom: 1px solid #E2E0DB;
    padding: 8px 6px;
  }
  th.num, td.num { text-align: right; }
  td {
    font-size: 13px;
    padding: 9px 6px;
    border-bottom: 1px dashed #EAE7E1;
  }
  .totals {
    margin-left: auto;
    max-width: 280px;
    font-size: 13px;
  }
  .totals .row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
  }
  .totals .grand {
    border-top: 2px solid #15171A;
    margin-top: 6px;
    padding-top: 8px;
    font-size: 17px;
    font-weight: 700;
  }
  .footer {
    margin-top: 26px;
    padding-top: 12px;
    border-top: 1px solid #E2E0DB;
    font-size: 11px;
    color: #5C6370;
    display: flex;
    justify-content: space-between;
  }
  @media print {
    body { padding: 0; }
    .sheet { border: none; padding: 0; }
  }
</style>
</head>
<body>
  <div class="sheet">
    <div class="header">
      <div>
        <h1 class="brand">${escHtml(opts.storeName)}</h1>
        ${opts.storeCity ? `<p class="city">${escHtml(opts.storeCity)}</p>` : ""}
      </div>
      <div class="meta">
        <div><strong>${escHtml(opts.docTitle)}</strong></div>
        <div>Ref: ${escHtml(opts.invoiceNo)}</div>
        <div>Date: ${escHtml(opts.dateStr)}</div>
      </div>
    </div>
    <div class="party">
      <div><strong>Party:</strong> ${escHtml(opts.customerLabel)}</div>
      <div><span class="badge">${escHtml(opts.paymentBadge)}</span></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Item / Particulars</th>
          <th class="num">Qty / Details</th>
          <th class="num">Amount</th>
        </tr>
      </thead>
      <tbody>
        ${opts.rowsHtml}
      </tbody>
    </table>
    <div class="totals">
      ${
        opts.totalAmount !== undefined
          ? `<div class="row grand"><span>Total Bill</span><span>${escHtml(formatINR(opts.totalAmount))}</span></div>`
          : ""
      }
      ${
        opts.paidAmount !== undefined && opts.totalAmount !== undefined && opts.paidAmount !== opts.totalAmount
          ? `<div class="row"><span>Paid</span><span>${escHtml(formatINR(opts.paidAmount))}</span></div>
             <div class="row"><span>Balance Due (Udhaar)</span><span>${escHtml(formatINR(opts.balanceDue ?? Math.max(0, opts.totalAmount - opts.paidAmount)))}</span></div>`
          : ""
      }
    </div>
    <div class="footer">
      <span>${escHtml(opts.footerNote)}</span>
      <span>Generated by Cue Ledger</span>
    </div>
  </div>
</body>
</html>`;
}

export function exportReceiptSlipAsPdf(
  receipt: ReceiptSlip,
  store?: { name?: string; city?: string }
): void {
  const storeName = store?.name?.trim() || "Cue Store";
  const rowsHtml = receipt.lines
    .map(
      (line) => `
      <tr>
        <td>${escHtml(line.label)}</td>
        <td class="num" colspan="2">${escHtml(line.value)}</td>
      </tr>`
    )
    .join("");

  const html = buildBillShell({
    storeName,
    storeCity: store?.city,
    docTitle: receipt.title,
    invoiceNo: formatShortOp(receipt.operationId),
    dateStr: receipt.transactionDate,
    customerLabel: receipt.subtitle || "Counter Bill",
    paymentBadge: receipt.status.toUpperCase(),
    rowsHtml,
    totalAmount: receipt.amountINR,
    footerNote: "Verified Ledger Slip",
  });
  triggerPrintableHtml(html, `${receipt.title} - ${receipt.transactionDate}`);
}

export function exportSaleBillAsPdf(
  sale: Sale,
  store?: { name?: string; city?: string }
): void {
  const storeName = store?.name?.trim() || "Cue Store";
  const paymentBadge =
    sale.paymentStatus === "credit"
      ? "UDHAAR"
      : sale.paymentStatus === "partial"
        ? "PARTIAL (SPLIT)"
        : sale.notes?.includes("[ONLINE]")
          ? "ONLINE / UPI"
          : sale.notes?.includes("[BANK]")
            ? "BANK"
            : "CASH";

  const rowsHtml =
    sale.items.length > 0
      ? sale.items
          .map(
            (it) => `
        <tr>
          <td>${escHtml(it.productName)}</td>
          <td class="num">${it.quantity} ${escHtml(it.unit)} × ${escHtml(formatINR(it.unitPrice))}</td>
          <td class="num">${escHtml(formatINR(it.lineTotal))}</td>
        </tr>`
          )
          .join("")
      : `<tr>
          <td>${escHtml(sale.notes?.replace(/\[[^\]]+\]/g, "").trim() || "Counter Sale / Khata Entry")}</td>
          <td class="num">1</td>
          <td class="num">${escHtml(formatINR(sale.totalAmount))}</td>
        </tr>`;

  const html = buildBillShell({
    storeName,
    storeCity: store?.city,
    docTitle: "TAX / RETAIL BILL",
    invoiceNo: formatShortOp(sale.operationId),
    dateStr: sale.transactionDate,
    customerLabel: sale.customerName || "Walk-in Customer",
    paymentBadge,
    rowsHtml,
    totalAmount: sale.totalAmount,
    paidAmount: sale.paidAmount,
    balanceDue: Math.max(0, sale.totalAmount - sale.paidAmount),
    footerNote: "Thank you for shopping with us!",
  });
  triggerPrintableHtml(html, `Bill_${formatShortOp(sale.operationId)}_${sale.transactionDate}`);
}
