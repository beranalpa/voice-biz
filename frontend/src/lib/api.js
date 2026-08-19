import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const getDashboard = () => axios.get(`${API}/dashboard`).then((r) => r.data);
export const getMemory = () => axios.get(`${API}/memory`).then((r) => r.data);
export const getBrief = () => axios.get(`${API}/brief`).then((r) => r.data);
export const parseText = (text) => axios.post(`${API}/nlu/parse`, { text }).then((r) => r.data);
export const commitDraft = (draft) => axios.post(`${API}/nlu/commit`, draft).then((r) => r.data);
export const resetDemo = () => axios.post(`${API}/demo/reset`).then((r) => r.data);

export const transcribe = (blob) => {
  const fd = new FormData();
  fd.append("audio", blob, "rekaman.webm");
  return axios.post(`${API}/voice/transcribe`, fd).then((r) => r.data);
};

export const rupiah = (n) => {
  const v = Math.round(Number(n || 0));
  return (v < 0 ? "-Rp" : "Rp") + Math.abs(v).toLocaleString("id-ID");
};

export const INTENT_LABELS = {
  sale: "Penjualan",
  expense: "Pengeluaran",
  receivable: "Piutang",
  receivable_payment: "Pembayaran utang",
  inventory: "Stok",
  customer: "Pelanggan",
  question: "Pertanyaan",
  unknown: "Belum dikenali",
};
