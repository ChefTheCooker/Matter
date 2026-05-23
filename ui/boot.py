# ============================================================
#  MATTER — ui/boot.py
#  Cinematic boot sequence. Plays before the main UI loads.
#  Call play(on_complete) from main.py before MatterUI.
# ============================================================

import tkinter as tk
import random
import time
import threading
import winsound


# ── Palette ───────────────────────────────────────────────
BG    = "#000000"
WHITE = "#ffffff"
DIM   = "#222222"
MID   = "#555555"

# ── Elite code vocabulary ─────────────────────────────────
CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()-_=+[]{}|;:,.<>?/\\~`"
KEYWORDS = [
    "0xFFB4A2E8", "SIGTERM::OVERRIDE", "malloc(0x7ffe0000)",
    "kernel_boot[0x3f]", "INIT::SYSCALL_TABLE", "0x00401000->0xC0FFEE",
    "RSA_2048::KEYGEN_COMPLETE", "AES_256_CBC::IV=0x4d617474657221",
    "SEGMENT_FAULT::RECOVERED", "0xDEADBEEF", "HEAP_ALLOC::0x7fff5fbff8a0",
    "STACK::OVERFLOW_PROTECTED", "THREAD_POOL::INIT[16]", "GPU::CUDA_CTX_INIT",
    "NEURAL_BRIDGE::SYNC_OK", "QUANTUM_SEED::0xF4E3D2C1B0A9",
    "MATTER_CORE::v2.0.1-RELEASE", "TENSOR_FLOW::GRAPH_COMPILED",
    "SYSCALL::execve('/matter/brain')", "PIPE::IPC_CHANNEL_OPEN",
    "CRYPTO::BLAKE3_HASH_VERIFIED", "NET::TLS1.3_HANDSHAKE_OK",
    "MATTER::CONSCIOUSNESS_LAYER_INIT", "SEMAPHORE::ACQUIRE[0x3]",
    "WATCHDOG::ARMED_T=30000ms", "BIOS::ACPI_TABLE_PARSED",
    "DMA::CHANNEL_4_ENABLED", "IRQ::VECTOR_TABLE_SET",
    "MATTER::SOUL_LOAD_COMPLETE", "BOOTLOADER::STAGE2_OK",
    "CIPHER::SERPENT_256_INIT", "ENTROPY_POOL::SEEDED",
    "MATTER::VOICE_ENGINE_ARMED", "GEMINI::BRIDGE_ESTABLISHED",
    "SCHEDULER::PRIORITY_SET[MAX]", "MATTER::READY",
]


def _rand_code_line() -> str:
    return random.choice([
        f"[{random.randint(0,9999):04d}] {random.choice(KEYWORDS)}",
        f"0x{random.randint(0,0xFFFFFFFF):08X}  >>  {random.choice(KEYWORDS)}",
        f"{''.join(random.choices(CHARS, k=random.randint(24,56)))}",
        f"MATTER::{random.choice(KEYWORDS).split('::')[-1]}  [{random.choice(['OK','DONE','ARMED','VERIFIED','LOCKED','SYNCED'])}]",
        f"[{time.strftime('%H:%M:%S')}::{random.randint(0,999):03d}] {random.choice(KEYWORDS)}",
        f"{''.join(random.choices('01', k=40))}  >>  {random.choice(KEYWORDS)}",
        f"PID={random.randint(1000,9999)}  MEM={random.randint(1,512)}MB  {random.choice(KEYWORDS)}",
    ])


class BootSequence:
    def __init__(self, on_complete):
        self.on_complete = on_complete

        self.root = tk.Tk()
        self.root.title("Matter")
        self.root.configure(bg=BG)
        self.root.attributes("-fullscreen", True)
        self.root.overrideredirect(True)

        self.W = self.root.winfo_screenwidth()
        self.H = self.root.winfo_screenheight()

        self.canvas = tk.Canvas(
            self.root, bg=BG,
            highlightthickness=0,
            width=self.W, height=self.H
        )
        self.canvas.pack(fill="both", expand=True)

        self.root.after(300, self._phase1_welcome)


    # ══════════════════════════════════════════════════════
    #  PHASE 1 — "Welcome to Matter" typing effect
    # ══════════════════════════════════════════════════════

    def _phase1_welcome(self):
        self.canvas.delete("all")
        self._type_target = "Welcome to Matter"
        self._type_idx    = 0

        self._welcome_id = self.canvas.create_text(
            self.W // 2, self.H // 2 - 24,
            text="",
            font=("Courier New", 32, "bold"),
            fill=WHITE, anchor="center"
        )
        self._sub_id = self.canvas.create_text(
            self.W // 2, self.H // 2 + 30,
            text="",
            font=("Courier New", 12),
            fill=DIM, anchor="center"
        )
        self._cursor_id = self.canvas.create_text(
            self.W // 2 + 10, self.H // 2 - 24,
            text="|",
            font=("Courier New", 32),
            fill=WHITE, anchor="center"
        )
        self._type_welcome()


    def _type_welcome(self):
        if self._type_idx <= len(self._type_target):
            typed = self._type_target[:self._type_idx]
            self.canvas.itemconfig(self._welcome_id, text=typed)
            # Move cursor to end of typed text
            approx_x = self.W // 2 - len(self._type_target) * 9 + self._type_idx * 18
            self.canvas.coords(self._cursor_id, approx_x, self.H // 2 - 24)
            self._type_idx += 1
            self.root.after(70, self._type_welcome)
        else:
            self.canvas.delete(self._cursor_id)
            self.canvas.itemconfig(self._sub_id, text="Enjoy Matter.")
            self.root.after(1400, self._phase2_code)


    # ══════════════════════════════════════════════════════
    #  PHASE 2 — Elite code flood
    # ══════════════════════════════════════════════════════

    def _phase2_code(self):
        self.canvas.delete("all")
        self._code_items  = []
        self._code_count  = 0
        self._line_h      = 20
        self._flood_code()


    def _flood_code(self):
        if self._code_count < 130:
            line  = _rand_code_line()
            color = random.choice([WHITE, WHITE, MID, DIM, "#888888"])
            size  = random.choice([9, 9, 10, 11])
            x     = random.randint(10, max(11, self.W - 400))

            for item_id in self._code_items:
                self.canvas.move(item_id, 0, self._line_h)

            new_id = self.canvas.create_text(
                x, 16,
                text=line,
                font=("Courier New", size),
                fill=color,
                anchor="w"
            )
            self._code_items.append(new_id)

            gone = [i for i in self._code_items
                    if self.canvas.coords(i) and self.canvas.coords(i)[1] > self.H + 10]
            for i in gone:
                self.canvas.delete(i)
                self._code_items.remove(i)

            self._code_count += 1
            self.root.after(35, self._flood_code)
        else:
            self.root.after(200, self._phase2b_boot_complete)


    def _phase2b_boot_complete(self):
        self.canvas.create_text(
            self.W // 2, self.H // 2,
            text="[ BOOT COMPLETE ]",
            font=("Courier New", 36, "bold"),
            fill=WHITE, anchor="center"
        )
        self.root.after(1100, self._phase3_blackout)


    # ══════════════════════════════════════════════════════
    #  PHASE 3 — Pure black silence (3 seconds)
    # ══════════════════════════════════════════════════════

    def _phase3_blackout(self):
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, self.W, self.H, fill=BG, outline="")
        self.root.after(3000, self._phase4_glitch)


    # ══════════════════════════════════════════════════════
    #  PHASE 4 — Glitch
    # ══════════════════════════════════════════════════════

    def _phase4_glitch(self):
        self._glitch_n = 0
        self._do_glitch()


    def _do_glitch(self):
        if self._glitch_n < 22:
            self.canvas.delete("all")
            self.canvas.create_rectangle(0, 0, self.W, self.H, fill=BG, outline="")

            for _ in range(random.randint(4, 12)):
                y      = random.randint(0, self.H)
                h      = random.randint(1, 28)
                offset = random.randint(-120, 120)
                col    = random.choice([WHITE, "#aaaaaa", "#444444", BG, BG])
                self.canvas.create_rectangle(
                    offset, y, self.W + offset, y + h,
                    fill=col, outline=""
                )

            for _ in range(random.randint(3, 8)):
                x = random.randint(0, self.W)
                y = random.randint(0, self.H)
                t = "".join(random.choices(CHARS, k=random.randint(6, 22)))
                self.canvas.create_text(
                    x, y, text=t,
                    font=("Courier New", random.randint(8, 18)),
                    fill=random.choice([WHITE, MID, DIM]),
                    anchor="w"
                )

            if random.random() > 0.35:
                offset_x = random.randint(-15, 15)
                offset_y = random.randint(-8, 8)
                self.canvas.create_text(
                    self.W // 2 + offset_x,
                    self.H // 2 + offset_y,
                    text="MATTER",
                    font=("Courier New", 80, "bold"),
                    fill=WHITE, anchor="center"
                )

            self._glitch_n += 1
            self.root.after(random.randint(35, 110), self._do_glitch)
        else:
            self.root.after(80, self._phase5_space)


    # ══════════════════════════════════════════════════════
    #  PHASE 5 — Space graph paper with MATTER
    # ══════════════════════════════════════════════════════

    def _phase5_space(self):
        self.canvas.delete("all")

        # Deep space bg
        self.canvas.create_rectangle(0, 0, self.W, self.H, fill="#000008", outline="")

        # Stars
        for _ in range(400):
            x  = random.randint(0, self.W)
            y  = random.randint(0, self.H)
            r  = random.choice([1, 1, 1, 1, 2])
            br = random.choice(["#ffffff", "#cccccc", "#888888", "#444444", "#222222"])
            self.canvas.create_oval(x, y, x+r, y+r, fill=br, outline="")

        # Graph paper grid
        gc = "#080818"
        gs = 44
        for x in range(0, self.W, gs):
            self.canvas.create_line(x, 0, x, self.H, fill=gc, width=1)
        for y in range(0, self.H, gs):
            self.canvas.create_line(0, y, self.W, y, fill=gc, width=1)

        # Subtle center glow rings
        for i in range(40, 0, -2):
            shade = max(0, min(255, i * 3))
            color = f"#0000{shade:02x}"
            try:
                self.canvas.create_oval(
                    self.W//2 - i*10, self.H//2 - i*4,
                    self.W//2 + i*10, self.H//2 + i*4,
                    outline=color, width=1
                )
            except Exception:
                pass

        # MATTER — massive centered
        self.canvas.create_text(
            self.W // 2, self.H // 2,
            text="MATTER",
            font=("Courier New", 110, "bold"),
            fill=WHITE, anchor="center"
        )

        # Tagline
        self.canvas.create_text(
            self.W // 2, self.H // 2 + 90,
            text="YOUR INTELLIGENCE. AMPLIFIED.",
            font=("Courier New", 13),
            fill="#2a2a2a", anchor="center"
        )

        # Sci-fi hum
        threading.Thread(target=self._play_hum, daemon=True).start()

        # Hold 5 seconds then fade out
        self.root.after(5000, self._phase6_fadeout)


    def _play_hum(self):
        try:
            sequence = [
                (55, 600), (65, 500), (80, 700),
                (100, 600), (80, 500), (65, 800),
                (55, 1000),
            ]
            for freq, dur in sequence:
                winsound.Beep(freq, dur)
        except Exception:
            pass


    # ══════════════════════════════════════════════════════
    #  PHASE 6 — Fade to black → launch main UI
    # ══════════════════════════════════════════════════════

    def _phase6_fadeout(self):
        self._fade_rects = []
        self._fade_step  = 0

        # Build overlay
        self._fade_overlay = self.canvas.create_rectangle(
            0, 0, self.W, self.H,
            fill=BG, outline="", stipple="gray75"
        )
        self._do_fade()


    def _do_fade(self):
        steps = ["gray75", "gray50", "gray25", "gray12", ""]
        if self._fade_step < len(steps):
            stipple = steps[self._fade_step]
            if stipple:
                self.canvas.itemconfig(self._fade_overlay, stipple=stipple)
            else:
                self.canvas.itemconfig(self._fade_overlay, stipple="")
            self._fade_step += 1
            self.root.after(250, self._do_fade)
        else:
            self.canvas.create_rectangle(
                0, 0, self.W, self.H, fill=BG, outline=""
            )
            self.root.after(500, self._finish)


    def _finish(self):
        self.root.destroy()
        self.on_complete()


    def run(self):
        self.root.mainloop()


# ── Public entry point ────────────────────────────────────

def play(on_complete):
    """
    Call this from main.py BEFORE launching MatterUI.

    Usage in main.py:
        from ui.boot import play

        if __name__ == "__main__":
            play(on_complete=start_matter)

    where start_matter() launches the main UI.
    """
    boot = BootSequence(on_complete=on_complete)
    boot.run()