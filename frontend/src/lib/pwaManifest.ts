/** Two installable apps on one origin: the public site (manifest scope "/") and the back
 *  office (public/admin.webmanifest, scope "/admin"). One SPA serves both, so the
 *  document's manifest link and the iOS home-screen title are switched by route —
 *  Chrome reads the manifest at install time, and iOS reads the meta tags of the page
 *  being added, so whichever app the visitor is standing in is the one they install.
 *  Only non-production builds register /admin routes, so production never switches. */
const PUBLIC = { manifest: '/manifest.webmanifest', title: '聽播客', icon: '/icons/pwa/apple-touch-icon.png' };
const ADMIN = { manifest: '/admin.webmanifest', title: '聽播客後台', icon: '/icons/pwa/admin/apple-touch-icon.png' };

export function isAdminPath(pathname: string): boolean {
  return pathname === '/admin' || pathname.startsWith('/admin/');
}

export function applyPwaManifest(pathname: string): void {
  const app = isAdminPath(pathname) ? ADMIN : PUBLIC;
  const head = document.head;
  let link = head.querySelector<HTMLLinkElement>('link[rel="manifest"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'manifest';
    head.appendChild(link);
  }
  if (link.getAttribute('href') !== app.manifest) link.setAttribute('href', app.manifest);
  head.querySelector('meta[name="apple-mobile-web-app-title"]')?.setAttribute('content', app.title);
  head.querySelector('link[rel="apple-touch-icon"]')?.setAttribute('href', app.icon);
}
