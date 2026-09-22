# Discord Bot

Bot Discord berbasis `discord.py` dengan slash command untuk memeriksa status
bot dan memilih anggota secara acak. Proyek ini menggunakan struktur modular
berbasis cog agar fitur baru dapat ditambahkan secara terpisah.

## Fitur

- `/ping` untuk memeriksa latency bot.
- `/ferra` untuk bertanya kepada asisten AI.
- `!ferra` untuk bertanya melalui prefix command di server atau DM.
- `/ferra` dapat digunakan di server dan DM bot.
- `/ferra`, `!ferra`, mention, dan reply dapat menerima attachment untuk dianalisis.
- `/choose-random-person` dengan wizard interaktif.
- Pemilihan satu atau beberapa anggota secara acak.
- Mode kandidat yang mendukung instalasi aplikasi untuk pengguna.
- Hasil privat dengan tombol untuk mengundi ulang atau mengakhiri sesi.

## Persiapan

1. Buat aplikasi dan bot melalui [Discord Developer Portal](https://discord.com/developers/applications).
2. Salin `.env.example` menjadi `.env`.
3. Isi `DISCORD_TOKEN` dengan token bot. Jangan membagikan token atau menyimpannya di repository.
4. Undang bot menggunakan scope `bot` dan `applications.commands`.
5. Untuk pemilihan otomatis, aktifkan **Server Members Intent** pada halaman
   Bot di Discord Developer Portal.

## Menjalankan

Di PowerShell:

```powershell
python -m venv .venv
\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

Setelah bot online, gunakan `/ping` pada server tempat bot telah diundang.

Untuk memakai Ferra melalui DM, buka DM dengan bot lalu gunakan `/ferra`,
`!ferra`, atau sebut bot diikuti pertanyaan. Bot harus sudah dapat menerima
pesan langsung dari akunmu, dan **Message Content Intent** perlu aktif untuk
format `!ferra` atau mention.

## Attachment

Ferra menerima satu attachment pada `/ferra`, serta attachment pada pesan
`!ferra`, mention, atau pesan yang direply. Batas setiap file adalah 10 MB.

Format yang dibaca langsung:

- TXT, Markdown, JSON, CSV, dan log.
- PDF, DOCX, XLSX/XLSM.
- Gambar untuk metadata format dan resolusi.
- Video/audio untuk metadata dasar; transkripsi dan pemahaman visual penuh
   belum dijalankan oleh model teks utama.

File rusak, terlalu besar, atau format yang belum didukung akan menghasilkan
peringatan di konteks AI, bukan membuat bot berhenti.

## Konfigurasi

```env
DISCORD_TOKEN=token_bot
DISCORD_MEMBERS_INTENT=false
FERRA_CREATOR_NAME=Taniki
BOT_OWNER_IDS=123456789012345678
```

Gunakan `DISCORD_MEMBERS_INTENT=true` jika ingin memakai mode pemilihan
otomatis dari server atau channel. Pastikan intent yang sama juga diaktifkan
di Discord Developer Portal.

## Role tool

AI memiliki tool terbatas untuk membaca role dan menambah atau menghapus satu
role dari satu member. Tool ini hanya berjalan di guild, memerlukan permission
`Manage Roles`, dan tetap tunduk pada hierarchy role Discord. Role `@everyone`,
managed role, role di atas atau setara dengan role bot, dan target sensitif
ditolak otomatis. Isi `BOT_OWNER_IDS` dengan Discord user ID owner bot jika
owner perlu melewati pemeriksaan hierarchy pemanggil; permission dan hierarchy
bot tetap wajib.

## Memilih orang secara acak

Jalankan `/choose-random-person`, tentukan jumlah orang, lalu ikuti wizard
interaktif berikut:

1. Tentukan jumlah orang yang ingin dipilih.
2. Pilih **Dari kandidat** untuk memilih hingga 10 orang melalui User Select.
3. Tekan **Konfirmasi** untuk menampilkan hasil.
4. Gunakan **Pilih lagi** untuk mengundi ulang pool yang sama, atau pilih **Selesai**.

Mode **Dari kandidat** dapat digunakan ketika aplikasi di-install untuk pengguna
dan hasilnya hanya terlihat oleh pemanggil command.

Mode **Otomatis** membutuhkan bot yang terpasang di server dan Server Members
Intent. Untuk voice channel, bot memilih anggota yang sedang berada di channel.
Untuk text channel, bot memilih anggota server yang memiliki izin melihat
channel tersebut. Instalasi aplikasi untuk pengguna tidak dapat mengambil daftar
anggota server secara otomatis; gunakan mode kandidat dalam kondisi tersebut.

Slash command global dapat memerlukan waktu beberapa menit untuk muncul setelah
sinkronisasi pertama.