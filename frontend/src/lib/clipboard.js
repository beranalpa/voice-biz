import { toast } from "sonner";

export const copyText = async (text, message = "Disalin") => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(message);
    return true;
  } catch {
    toast.error("Browser memblokir penyalinan. Tekan lama teksnya untuk menyalin manual.");
    return false;
  }
};
