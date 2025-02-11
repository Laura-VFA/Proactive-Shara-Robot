# Shara Proactive Robot
*THIS IS A SECOND VERSION OF THE [EVA ROBOT](https://github.com/Laura-VFA/Affective-Proactive-EVA-Robot)*.  
Shara is a **social 🗣 and affective ❤️ robot**. It is not only a passive assistant, but an active one: **proactive behaviour** is incorporated in the robot. It can start conversations and show concern about the user, making the interaction more natural and affective.  
This repo contains the *brain* 🧠 structure of the robot, the proactive and interaction behavior themselves.



<p align="center">
  <img src="https://github.com/user-attachments/assets/3c898751-434d-42ab-8865-fbc9937a91e2" width="300">
</p>

## Be different 😎
With SHARA, you can have conversations in the more natural way. It is activated by a novel method called wakeface, in which the robot activates/listens the user by looking at it. Also, it is able to start conversations by using proactive questions.

Highlighted proactive questions ✨ how are you, who are you

## Main components 🤖🛠️

*Shara hardware structure is based on the existing EVA robotic platform, but with several modifications.* This EVA affective and proactive version is constructed using the following elements:
- 🖥️ [Screen Waveshare 7inch HDMI LCD (H)](https://www.waveshare.com/7inch-HDMI-LCD-H.htm) for 👀 displaying
- 📷 [IMX219-160IR Camera](https://www.waveshare.com/wiki/IMX219-160IR_Camera) 
- 🎙️ [ReSpeaker Mic Array v2.0](https://wiki.seeedstudio.com/ReSpeaker_Mic_Array_v2.0/)
- 🔊 [Speakers](https://www.waveshare.com/8ohm-5w-speaker.htm)
- 🤖 [Raspberry Pi 5 16GB](https://www.waveshare.com/raspberry-pi-5.htm?sku=30141) (remember to use cooler heatsinks 🔥)
- 🔃 [2x Stepper motor 28BYJ-48](https://www.prometec.net/motor-28byj-48/) for the neck
- 💡 [Neopixel LED RGB ring 24 bits WS2812](https://www.amazon.es/Anillo-WS2812-l%C3%A1mpara-controladores-integrados/dp/B07QLMPV6S?__mk_es_ES=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=VI4O367CVZVS&keywords=neopixel+24&qid=1673225765&sprefix=neopixel+24%2Caps%2C110&sr=8-27), controlled by ESP32 [ESP-WROOM-32](https://www.amazon.es/AZDelivery-ESP-WROOM-32-Bluetooth-Desarrollo-Incluido/dp/B071P98VTG?th=1) and [WLED project](https://github.com/wled-dev/WLED)!
- 🪭 [Noctua NF-A8 5V PWM fan](https://www.amazon.es/dp/B07DXMF32M?ref=cm_sw_r_cso_wa_apan_dp_FS4FP477BN7KAVQ29CQG)
- Plastic structure printed using 3D printer [repository of the 3D models here!] [WIP]

## Installation ⚙️

### Requirements

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install all the pre-requisites.

```bash
pip3 install -r requirements.txt
```

### Google and OpenAI services
Ensure you have [Google Cloud](https://console.cloud.google.com/) and [OpenAI](https://platform.openai.com/) accounts.  

It is necessary to have *apikeys* 🔑 for the following services:
- [Google Speech to Text](https://cloud.google.com/speech-to-text/docs/libraries)
- [Google Text to Speech](https://cloud.google.com/text-to-speech/docs/libraries)
- [OpenAI Text Generation](https://platform.openai.com/docs/guides/text-generation) for conversation generation with Shara

Google project credentials' file files must be stored in a ```credentials/``` directory, located **outside** the main project directory:
```bash
$ any_directory
.
├── credentials
│   └── google_credentials.json
└── Proactive-Shara-Robot/
```
In this case, by-default environment variables provided by Google and OpenAI (*GOOGLE_APPLICATION_CREDENTIALS* and *OPENAI_API_KEY*) are used for automatic services apikey authentication (easier!).


## Usage 🚀

For executing SHARA, you only have to run from root repo directory:
```bash
python3 main.py
```
*➡️**Note**: proactive_phrases.json and shara_prompt.txt contain instructions **totally in spanish**, so if you want SHARA to speak in a different language, teach it your language by changing these files in your language. She will be happy to learn it 😊*

And that's how you construct your own affective social robot! 🤖❤️👩🏻


## Authors 📝
- [Laura Villa 🦁](https://github.com/Laura-VFA)
