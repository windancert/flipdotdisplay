"""A small two-layer grid router (A* over a 0.635 mm grid, 45-degree moves), with
rip-up and reroute.

Pure Python, no KiCad imports. Clearances are checked against the centres of
grid cells, with a small margin; KiCad's DRC is the final check.
"""
import heapq
import math

F, B = 0, 1
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
SQ2 = math.sqrt(2)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


class Obj:
    """Copper (or a keep-out) that other nets must clear."""
    __slots__ = ("net", "layers", "kind", "g", "hw", "clr")

    def __init__(self, net, layers, kind, g, hw, clr):
        self.net, self.layers, self.kind, self.g, self.hw, self.clr = net, layers, kind, g, hw, clr

    def dist(self, x, y):
        k, g = self.kind, self.g
        if k == "circle":
            return max(0.0, math.hypot(x - g[0], y - g[1]) - self.hw)
        if k == "rect":  # g = cx, cy, hx, hy
            dx = max(abs(x - g[0]) - g[2], 0.0)
            dy = max(abs(y - g[1]) - g[3], 0.0)
            return math.hypot(dx, dy)
        if k == "seg":
            return max(0.0, seg_dist(x, y, *g) - self.hw)
        raise ValueError(k)

    def bbox(self):
        k, g = self.kind, self.g
        if k == "circle":
            return g[0] - self.hw, g[1] - self.hw, g[0] + self.hw, g[1] + self.hw
        if k == "rect":
            return g[0] - g[2], g[1] - g[3], g[0] + g[2], g[1] + g[3]
        return (min(g[0], g[2]) - self.hw, min(g[1], g[3]) - self.hw,
                max(g[0], g[2]) + self.hw, max(g[1], g[3]) + self.hw)


class Router:
    def __init__(self, width, height, grid=0.635, edge_clearance=0.5, margin=0.05):
        self.g = grid
        self.nx = int(width / grid) + 1
        self.ny = int(height / grid) + 1
        self.W, self.H = width, height
        self.edge = edge_clearance
        self.margin = margin
        self.pad_objs = []    # pads and hole keep-outs, never move
        self.pads = {}        # net -> list of pad Obj
        self.routed = {}      # net -> list of Obj (tracks and vias)
        self.keepouts = []    # polygons: no tracks, no vias
        self.via_keepouts = []  # rectangles (x0, y0, x1, y1): no vias
        self.cost_zones = []  # (x0, y0, x1, y1, factor)
        self.rules = {}       # net -> (track width, clearance, via diameter, via drill)
        self.default_rule = (0.3, 0.2, 0.6, 0.3)
        self.result_edges = {}  # net -> set of (layer, cell_a, cell_b)
        self.result_vias = {}   # net -> set of cell
        self.wrong_way = 2.0     # cost factor for F horizontal / B vertical moves
        self.diag_factor = 1.25
        self.via_cost = 4.0
        self._static = {}
        self._cmap = None

    # ---- setup -------------------------------------------------------------
    def add_pad(self, net, kind, g, hw=0.0, clr=0.2):
        o = Obj(net, (F, B), kind, g, hw, clr)
        self.pad_objs.append(o)
        if net:
            self.pads.setdefault(net, []).append(o)
        return o

    def rule(self, net):
        return self.rules.get(net, self.default_rule)

    # ---- grid helpers ------------------------------------------------------
    def xy(self, i, j):
        return i * self.g, j * self.g

    def cells_in(self, o):
        """Cells whose centres lie inside a pad."""
        x0, y0, x1, y1 = o.bbox()
        out = []
        for j in range(max(0, int(y0 / self.g)), min(self.ny, int(y1 / self.g) + 2)):
            for i in range(max(0, int(x0 / self.g)), min(self.nx, int(x1 / self.g) + 2)):
                x, y = self.xy(i, j)
                if o.dist(x, y) <= 1e-9:
                    out.append(j * self.nx + i)
        if not out:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            out.append(round(cy / self.g) * self.nx + round(cx / self.g))
        return out

    def _cells_near(self, o, R):
        """Cells within R of an object's copper."""
        g, nx = self.g, self.nx
        x0, y0, x1, y1 = o.bbox()
        i0, i1 = max(0, int((x0 - R) / g)), min(nx - 1, int((x1 + R) / g) + 1)
        j0, j1 = max(0, int((y0 - R) / g)), min(self.ny - 1, int((y1 + R) / g) + 1)
        out = []
        for j in range(j0, j1 + 1):
            y = j * g
            for i in range(i0, i1 + 1):
                if o.dist(i * g, y) < R:
                    out.append(j * nx + i)
        return out

    def _static_maps(self, net):
        """Blocking from pads of other nets, the board edge and keep-outs."""
        if net in self._static:
            return self._static[net]
        w, clr, vd, _ = self.rule(net)
        hw, vr, m = w / 2, vd / 2, self.margin
        n = self.nx * self.ny
        tb = bytearray(n)
        vb = bytearray(n)
        for o in self.pad_objs:
            if o.net == net and net is not None:
                continue
            for c in self._cells_near(o, hw + max(clr, o.clr) + m):
                tb[c] = 1
            for c in self._cells_near(o, vr + max(clr, o.clr) + m):
                vb[c] = 1
        g = self.g
        for j in range(self.ny):
            for i in range(self.nx):
                x, y = i * g, j * g
                d = min(x, y, self.W - x, self.H - y)
                idx = j * self.nx + i
                if d < self.edge + hw:
                    tb[idx] = 1
                if d < self.edge + vr:
                    vb[idx] = 1
                for (x0, y0, x1, y1) in self.via_keepouts:
                    if x0 - vr - 0.1 <= x <= x1 + vr + 0.1 and y0 - vr - 0.1 <= y <= y1 + vr + 0.1:
                        vb[idx] = 1
                for poly in self.keepouts:
                    if point_in_poly(x, y, poly) or min(
                            seg_dist(x, y, *poly[k], *poly[(k + 1) % len(poly)])
                            for k in range(len(poly))) < max(hw, vr) + 0.1:
                        tb[idx] = vb[idx] = 1
        self._static[net] = (tb, vb)
        return tb, vb

    def _dynamic(self, net):
        """Other nets' tracks and vias, as owner maps: per layer {cell: set(nets)} for
        where this net's track may not go, and {cell: set(nets)} for its vias."""
        w, clr, vd, _ = self.rule(net)
        hw, vr, m = w / 2, vd / 2, self.margin
        tmap = [{}, {}]
        vmap = {}
        for other, objs in self.routed.items():
            if other == net:
                continue
            for o in objs:
                for c in self._cells_near(o, hw + max(clr, o.clr) + m):
                    for L in o.layers:
                        tmap[L].setdefault(c, set()).add(other)
                for c in self._cells_near(o, vr + max(clr, o.clr) + m):
                    vmap.setdefault(c, set()).add(other)
        return tmap, vmap

    def cost_map(self):
        if self._cmap is None:
            c = [1.0] * (self.nx * self.ny)
            for (x0, y0, x1, y1, f) in self.cost_zones:
                for j in range(max(0, int(y0 / self.g)), min(self.ny, int(y1 / self.g) + 1)):
                    for i in range(max(0, int(x0 / self.g)), min(self.nx, int(x1 / self.g) + 1)):
                        c[j * self.nx + i] = max(c[j * self.nx + i], f)
            self._cmap = c
        return self._cmap

    # ---- routing -----------------------------------------------------------
    def route_net(self, net, soft_penalty=None):
        """Route one net. With soft_penalty ({net: cost}), other nets' copper may be
        crossed at that cost: nothing is committed and the set of crossed nets is
        returned (None if even that fails). Otherwise returns True/False and commits."""
        soft = soft_penalty is not None
        pads = self.pads.get(net, [])
        if len(pads) < 2:
            if soft:
                return set()
            self._commit(net, set(), set())
            return True
        nx, ny = self.nx, self.ny
        n = nx * ny
        stb, svb = self._static_maps(net)
        tmap, vmap = self._dynamic(net)
        tblock = [bytearray(stb), bytearray(stb)]
        tpen = [{}, {}]
        vpen = {}
        for L in (F, B):
            for c, owners in tmap[L].items():
                if soft:
                    tpen[L][c] = sum(soft_penalty.get(o, 30.0) for o in owners)
                else:
                    tblock[L][c] = 1
        via_ok = bytearray(1 - b for b in svb)
        for c, owners in vmap.items():
            if soft:
                vpen[c] = sum(soft_penalty.get(o, 30.0) for o in owners)
            else:
                via_ok[c] = 0
        cmap = self.cost_map()
        pad_cells = [set(self.cells_in(p)) for p in pads]
        own_pad = set().union(*pad_cells)
        edges = set()
        vias = set()
        tree = {(F, c) for c in pad_cells[0]} | {(B, c) for c in pad_cells[0]}
        remaining = set(range(1, len(pads)))
        wrong, diag, via_cost = self.wrong_way, SQ2 * self.diag_factor, self.via_cost
        while remaining:
            target = {}
            for k in remaining:
                for c in pad_cells[k]:
                    target[c] = k
            ti = [c % nx for c in target]
            tj = [c // nx for c in target]
            bx0, bx1, by0, by1 = min(ti), max(ti), min(tj), max(tj)

            def h(c):
                i, j = c % nx, c // nx
                dx = max(bx0 - i, 0, i - bx1)
                dy = max(by0 - j, 0, j - by1)
                return max(dx, dy) + (SQ2 - 1) * min(dx, dy)

            dist = {}
            prev = {}
            heap = []
            for (L, c) in tree:
                s = (L, c, 8)
                dist[s] = 0.0
                heapq.heappush(heap, (h(c), 0.0, s))
            found = None
            while heap:
                f, d, s = heapq.heappop(heap)
                if d > dist.get(s, 1e18):
                    continue
                L, c, dr = s
                if c in target and (L, c) not in tree:
                    found = s
                    break
                i, j = c % nx, c // nx
                blk = tblock[L]
                pen = tpen[L]
                for nd in range(8):
                    if dr != 8:
                        turn = min((nd - dr) % 8, (dr - nd) % 8)
                        if turn > 2:
                            continue
                        tp = (0.0, 0.35, 1.0)[turn]
                    else:
                        tp = 0.0
                    di, dj = DIRS[nd]
                    ni, nj = i + di, j + dj
                    if not (0 <= ni < nx and 0 <= nj < ny):
                        continue
                    nc = nj * nx + ni
                    if blk[nc]:
                        continue
                    if di and dj:
                        if blk[j * nx + ni] or blk[nj * nx + i]:
                            continue
                        dirf = diag
                        if pen:
                            tp += pen.get(j * nx + ni, 0.0) + pen.get(nj * nx + i, 0.0)
                    elif (L == F) == (dj == 0):  # F prefers vertical, B horizontal
                        dirf = wrong
                    else:
                        dirf = 1.0
                    step = dirf * cmap[nc] + tp
                    if pen:
                        step += pen.get(nc, 0.0)
                    ns = (L, nc, nd)
                    nd_ = d + step
                    if nd_ < dist.get(ns, 1e18):
                        dist[ns] = nd_
                        prev[ns] = s
                        heapq.heappush(heap, (nd_ + h(nc), nd_, ns))
                # layer change
                if c in own_pad:
                    vc = 0.0
                elif via_ok[c] and not tblock[1 - L][c]:
                    vc = via_cost + vpen.get(c, 0.0) + tpen[1 - L].get(c, 0.0)
                else:
                    continue
                ns = (1 - L, c, 8)
                nd_ = d + vc
                if nd_ < dist.get(ns, 1e18):
                    dist[ns] = nd_
                    prev[ns] = s
                    heapq.heappush(heap, (nd_ + h(c), nd_, ns))
            if found is None:
                return None if soft else False
            s = found
            k = target[found[1]]
            while s in prev:
                p = prev[s]
                if p[0] != s[0]:
                    if s[1] not in own_pad:
                        vias.add(s[1])
                else:
                    edges.add((s[0], min(p[1], s[1]), max(p[1], s[1])))
                tree.add((s[0], s[1]))
                s = p
            tree.add((found[0], found[1]))
            for c in pad_cells[k]:
                tree.add((F, c))
                tree.add((B, c))
            for c in vias:
                tree.add((F, c))
                tree.add((B, c))
            remaining.discard(k)
        if soft:
            crossed = set()
            for (L, a, b) in edges:
                cells = [a, b]
                if a % nx != b % nx and a // nx != b // nx:  # diagonal: its corners too
                    cells += [(a // nx) * nx + b % nx, (b // nx) * nx + a % nx]
                for c in cells:
                    crossed |= tmap[L].get(c, set())
            for c in vias:
                crossed |= vmap.get(c, set()) | tmap[F].get(c, set()) | tmap[B].get(c, set())
            return crossed
        self._commit(net, edges, vias)
        return True

    def _commit(self, net, edges, vias):
        w, clr, vd, _ = self.rule(net)
        objs = []
        for (L, a, b) in edges:
            ax, ay = self.xy(a % self.nx, a // self.nx)
            bx, by = self.xy(b % self.nx, b // self.nx)
            objs.append(Obj(net, (L,), "seg", (ax, ay, bx, by), w / 2, clr))
        for c in vias:
            x, y = self.xy(c % self.nx, c // self.nx)
            objs.append(Obj(net, (F, B), "circle", (x, y), vd / 2, clr))
        self.routed[net] = objs
        self.result_edges[net] = edges
        self.result_vias[net] = vias

    def rip(self, net):
        self.routed.pop(net, None)
        self.result_edges.pop(net, None)
        self.result_vias.pop(net, None)

    def route_all(self, order, max_rounds=200, log=print):
        """Route in order. A net that cannot get through rips up the nets in its way,
        which then go to the back of the queue."""
        queue = list(order)
        ripped = {}
        failed = set()
        rounds = 0
        while queue and rounds < max_rounds:
            rounds += 1
            net = queue.pop(0)
            if self.route_net(net):
                failed.discard(net)
                continue
            pen = {o: 30.0 + 40.0 * ripped.get(o, 0) for o in self.routed}
            crossed = self.route_net(net, soft_penalty=pen)
            if crossed is None or not crossed:
                log(f"  {net}: no path even through other nets ({crossed})")
                failed.add(net)
                continue
            log(f"  {net}: ripping {sorted(crossed)}")
            for o in crossed:
                self.rip(o)
                ripped[o] = ripped.get(o, 0) + 1
            if self.route_net(net):
                failed.discard(net)
            else:
                queue.append(net)
            for o in crossed:
                if o not in queue:
                    queue.append(o)
        failed |= set(queue)
        failed |= {n for n in order if n not in self.routed}
        return sorted(failed)

    def segments(self, net):
        """Merge unit grid steps into straight segments: [(layer, x0, y0, x1, y1)]."""
        edges = self.result_edges.get(net, set())
        out = []
        for L in (F, B):
            adj = {}
            for (l, a, b) in edges:
                if l != L:
                    continue
                adj.setdefault(a, []).append(b)
                adj.setdefault(b, []).append(a)
            seen = set()

            def direction(a, b):
                return (b % self.nx - a % self.nx, b // self.nx - a // self.nx)

            def interior(n):
                nb = adj[n]
                return len(nb) == 2 and direction(nb[0], n) == direction(n, nb[1])

            for a in [n for n in adj if not interior(n)]:
                for b in adj[a]:
                    if (min(a, b), max(a, b)) in seen:
                        continue
                    seen.add((min(a, b), max(a, b)))
                    prev, cur = a, b
                    while interior(cur):
                        nxt = adj[cur][0] if adj[cur][0] != prev else adj[cur][1]
                        seen.add((min(cur, nxt), max(cur, nxt)))
                        prev, cur = cur, nxt
                    x0, y0 = self.xy(a % self.nx, a // self.nx)
                    x1, y1 = self.xy(cur % self.nx, cur // self.nx)
                    out.append((L, x0, y0, x1, y1))
        return out

    def via_points(self, net):
        return [self.xy(c % self.nx, c // self.nx) for c in self.result_vias.get(net, ())]
