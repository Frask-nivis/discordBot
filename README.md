# Discord Bot

Bot Discord sederhana berbasis `discord.py` dengan slash command `/ping` dan
`/choose-random-person`.

## Persiapan

1. Buat aplikasi dan bot di [Discord Developer Portal](https://discord.com/developers/applications).
2. Salin `.env.example` menjadi `.env`.
3. Isi `DISCORD_TOKEN` dengan token bot. Jangan membagikan atau melakukan commit terhadap token ini.
4. Saat membuat invite URL, gunakan scope `bot` dan `applications.commands`.
5. Untuk mode otomatis, aktifkan **Server Members Intent** di halaman Bot pada
	Discord Developer Portal dan ubah `DISCORD_MEMBERS_INTENT=true` di `.env`.

## Menjalankan

Di PowerShell:

```powershell
python -m venv .venv
\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

Setelah bot online, gunakan `/ping` di server Discord yang sudah diundang bot.

## Memilih orang secara acak

Gunakan `/choose-random-person` lalu ikuti wizard ephemeral:

1. Tentukan jumlah orang yang ingin dipilih.
2. Pilih **Dari kandidat** untuk membuka User Select dan memilih hingga 10 orang.
3. Tekan **Konfirmasi** untuk melihat hasil dalam embed.
4. Gunakan **Pilih lagi** untuk mengundi ulang kandidat yang sama, atau **Selesai**.

Mode **Dari kandidat** bekerja untuk self-install app dan hasilnya hanya terlihat
oleh pemanggil command.

Mode **Otomatis dari server/channel** membutuhkan bot ter-install di server
dan Server Members Intent. Untuk voice channel, bot memilih member yang sedang
berada di channel. Untuk text channel, bot memilih member server yang memiliki
izin melihat channel tersebut. Self-install app tidak dapat mengambil daftar
member server secara otomatis, sehingga gunakan mode kandidat.

Slash command global dapat memerlukan waktu beberapa menit untuk muncul setelah sinkronisasi pertama.