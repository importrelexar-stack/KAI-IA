export function navigate(route: string, param?: string) {
  location.hash = `/${route}${param ? `/${param}` : ""}`;
}
