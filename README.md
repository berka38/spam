# Telegram Grup Yönetim Botu

Bu proje, Telegram gruplarındaki kullanıcıları yönetmek için iki farklı uygulama içerir: bir telegram botu (bot.py) ve bir userbot (userbot.py).

## Özellikler

- Bir gruptaki kişilerin ID bilgilerini toplama
- ID bilgileri bulunan kişilere tek tek özel mesaj gönderme
- Bir gruptaki kişilere tek tek belirli bir mesajı gönderme
- Bir gruptaki üyeleri belirlenen başka bir gruba çekme
- ID'leri bulunan kişileri bir gruba çekme

## Bot vs UserBot

- **Bot (bot.py)**: Normal bir Telegram botu. Kolay kurulum, ancak Telegram API kısıtlamaları nedeniyle sadece grup yöneticilerinin bilgilerini toplayabilir.
- **UserBot (userbot.py)**: Kullanıcı hesabı üzerinden çalışır. Tüm grup üyelerine erişebilir ve işlem yapabilir.

## Kurulum

1. Python 3.7 veya daha yüksek bir sürüm yükleyin.
2. Gerekli kütüphaneleri yükleyin:
   ```
   pip install -r requirements.txt
   ```

### Bot Kurulumu
1. [BotFather](https://t.me/BotFather) üzerinden bir Telegram botu oluşturun ve API token alın.
2. `bot.py` dosyasındaki `YOUR_BOT_TOKEN` kısmını, aldığınız API token ile değiştirin.

### UserBot Kurulumu
1. [my.telegram.org](https://my.telegram.org) adresine giderek API ID ve API Hash alın.
2. `userbot.py` dosyasındaki `API_ID` ve `API_HASH` değişkenlerini kendi değerlerinizle değiştirin.

## Kullanım

### Bot Kullanımı
```
python bot.py
```

### UserBot Kullanımı
```
python userbot.py
```

İlk çalıştırmada telefon numaranızı ve gelen doğrulama kodunu girmeniz gerekecektir.

## Komutlar

Her iki uygulamada da aynı komutlar geçerlidir:

- `/start` - Ana menüyü gösterir (sadece bot)
- `/collect_ids <group_id>` - Bir gruptan kullanıcı ID'lerini toplar
- `/send_pm <message>` - Toplanan ID'lere özel mesaj gönderir
- `/send_group <group_id> <message>` - Bir gruptaki tüm kullanıcılara mesaj gönderir
- `/move <source_group_id> <target_group_id>` - Bir gruptaki üyeleri başka bir gruba çeker
- `/add_to_group <group_id>` - Toplanan ID'leri bir gruba ekler
- `/help` - Yardım mesajını gösterir

## Grup ID'si Nasıl Bulunur?

1. Web üzerinden Telegram'a giriş yapın (web.telegram.org)
2. İstediğiniz gruba tıklayın
3. URL'de görünen sayı grup ID'sidir. Örneğin: `https://web.telegram.org/a/#-1001234567890` adresindeki `-1001234567890` grup ID'sidir.

## Güvenlik Uyarısı

UserBot kullanımı, Telegram Hizmet Şartları'na aykırı olabilir. Spam veya kötü amaçlı kullanım için değil, sadece meşru amaçlar için kullanın. Hesabınızın yasaklanmasına neden olabilecek davranışlardan kaçının. 