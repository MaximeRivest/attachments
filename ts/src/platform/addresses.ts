/**
 * Which IP addresses are public: Python's `ipaddress` `is_global` (3.12),
 * the IANA special-purpose registries. An IPv4-mapped IPv6 address is
 * judged as its IPv4 address.
 *
 * @internal
 */

type Net = readonly [bits: bigint, prefix: number];

function v4(text: string): bigint | null {
  const parts = text.split(".");
  if (parts.length !== 4) return null;
  let n = 0n;
  for (const p of parts) {
    if (!/^[0-9]{1,3}$/u.test(p) || Number(p) > 255) return null;
    n = (n << 8n) | BigInt(Number(p));
  }
  return n;
}

function v6(text: string): bigint | null {
  let s = text.split("%")[0]!.toLowerCase();
  // A trailing dotted IPv4 part.
  const dotted = /^(.*:)(\d+\.\d+\.\d+\.\d+)$/u.exec(s);
  if (dotted) {
    const tail = v4(dotted[2]!);
    if (tail === null) return null;
    s = `${dotted[1]}${((tail >> 16n) & 0xffffn).toString(16)}:${(tail & 0xffffn).toString(16)}`;
  }
  const halves = s.split("::");
  if (halves.length > 2) return null;
  const head = halves[0] ? halves[0].split(":") : [];
  const tail = halves.length === 2 && halves[1] ? halves[1].split(":") : [];
  const missing = 8 - head.length - tail.length;
  if (halves.length === 1 ? head.length !== 8 : missing < 1) return null;
  const groups = [...head, ...Array<string>(halves.length === 2 ? missing : 0).fill("0"), ...tail];
  let n = 0n;
  for (const g of groups) {
    if (!/^[0-9a-f]{1,4}$/u.test(g)) return null;
    n = (n << 16n) | BigInt(parseInt(g, 16));
  }
  return n;
}

function nets(list: string[], parse: (s: string) => bigint | null, width: number): Net[] {
  return list.map((cidr) => {
    const [addr, prefix] = cidr.split("/") as [string, string];
    const bits = parse(addr)!;
    return [bits >> BigInt(width - Number(prefix)), Number(prefix)] as const;
  });
}

const within = (n: bigint, width: number, [bits, prefix]: Net): boolean => n >> BigInt(width - prefix) === bits;

const V4_PRIVATE = nets(
  ["0.0.0.0/8", "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.0.170/31",
    "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4",
    "255.255.255.255/32"],
  v4,
  32,
);
const V4_EXCEPTIONS = nets(["192.0.0.9/32", "192.0.0.10/32"], v4, 32);
const V4_SHARED = nets(["100.64.0.0/10"], v4, 32);
const V6_PRIVATE = nets(
  ["::1/128", "::/128", "::ffff:0:0/96", "64:ff9b:1::/48", "100::/64", "2001::/23", "2001:db8::/32", "2002::/16",
    "3fff::/20", "fc00::/7", "fe80::/10"],
  v6,
  128,
);
const V6_EXCEPTIONS = nets(
  ["2001:1::1/128", "2001:1::2/128", "2001:3::/32", "2001:4:112::/48", "2001:20::/28", "2001:30::/28"],
  v6,
  128,
);

function v4Global(n: bigint): boolean {
  if (V4_SHARED.some((net) => within(n, 32, net))) return false;
  return !(V4_PRIVATE.some((net) => within(n, 32, net)) && !V4_EXCEPTIONS.some((net) => within(n, 32, net)));
}

/** Whether `address` (IPv4 or IPv6 text) is public. Text that is not an address is not. */
export function isGlobal(address: string): boolean {
  const four = v4(address);
  if (four !== null) return v4Global(four);
  const six = v6(address);
  if (six === null) return false;
  if (six >> 32n === 0xffffn) return v4Global(six & 0xffffffffn);
  return !(V6_PRIVATE.some((net) => within(six, 128, net)) && !V6_EXCEPTIONS.some((net) => within(six, 128, net)));
}

/** Whether `host` is written as an IP address (a URL's hostname, brackets removed). */
export function isAddress(host: string): boolean {
  return v4(host) !== null || v6(host) !== null;
}
