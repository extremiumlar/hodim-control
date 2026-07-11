/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // hodim_crm hodimlar_tizimi ostiga "/verifix" URL prefiksi bilan ulanadi
  // (nginx reverse-proxy: domen/verifix/ -> shu ilova). basePath barcha sahifa,
  // route (/django-api ham) va statik assetlarga /verifix qo'shadi.
  basePath: "/verifix",
  // Django URL'lari oxirida / ishlatadi (APPEND_SLASH) -
  // Next.js / ni o'chirib 308 redirect qilmasligi uchun:
  skipTrailingSlashRedirect: true,
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "http", hostname: "127.0.0.1" },
    ],
  },
};

module.exports = nextConfig;
