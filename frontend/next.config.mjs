/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // NEXT_PUBLIC_API_URL build-time'da yoksa runtime'daki window.ENV'ye de bakılabilir
  // Varsayılan http://localhost:8000 bileşen içinde zaten tanımlı
}

export default nextConfig
