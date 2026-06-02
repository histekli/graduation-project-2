import dynamic from "next/dynamic";

// SSR kapalı — bileşen tarayıcı API'lerini kullanıyor (fetch, AbortController, Blob)
const DeanOfficeHelper = dynamic(
  () => import("../src/components/DeanOfficeHelper"),
  { ssr: false }
);

export default function Home() {
  return <DeanOfficeHelper />;
}
