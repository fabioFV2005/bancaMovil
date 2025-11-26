/*
  sistema_cobros_esp32.cpp
  Código completo para ESP32:
  - Keypad 4x4
  - LCD I2C 20x4
  - Lector RFID MFRC522
  - Conexión a backend FastAPI (endpoints: /buscar_usuario_por_ci, /registrar_tarjeta, /transaccion, /consultar_saldo)

  Comentarios muy resumidos antes de cada función/variable.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Keypad.h>
#include <LiquidCrystal_I2C.h>
#include <SPI.h>
#include <MFRC522.h>

// ---------- CONFIG ----------
// WiFi
#define WIFI_SSID "FLIA RIVERO"
#define WIFI_PASSWORD "17030522"

// Backend
#define API_HOST "http://192.168.0.4:8000" // esto tenemos que cambiarlo con algunoa conexion o hacerlo estatico xd
#define ID_TARJETERO 1

#define RST_PIN 16
#define SS_PIN 17
MFRC522 rfid(SS_PIN, RST_PIN);

const byte ROWS = 4;
const byte COLS = 4;
char keys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
byte rowPins[ROWS] = {25, 26, 27, 14};       
byte colPins[COLS] = {32, 33, 13, 12};        
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

// LCD I2C 20x4
LiquidCrystal_I2C lcd(0x27, 20, 4);

// ---------- ESTADOS ----------
enum Estado {
  MENU_PRINCIPAL,
  INGRESO_MONTO,
  ESPERANDO_TARJETA_PAGO,
  INGRESO_PIN_PAGO,
  INGRESO_CI_REGISTRO,
  ESPERANDO_TARJETA_REGISTRO,
  INGRESO_PIN_REGISTRO,
  CONSULTANDO_SALDO
};
Estado estadoActual = MENU_PRINCIPAL;

// ---------- VARIABLES GLOBALES ----------
float saldoCaja = 0.0;
float montoTemp = 0.0;
String uidTemp = "";
String pinTemp = "";
String ciTemp = "";
String nombreUsuario = "";
bool wifiConectado = false;

// ---------- PROTOTIPOS ----------
void conectarWiFi();
void cargarDatosIniciales();
void mostrarMenuPrincipal();
void procesarMenuPrincipal(char tecla);
void iniciarTransferencia();
void procesarIngresoMonto(char tecla);
void actualizarDisplayMonto(String montoStr);
void esperarTarjetaParaPago();
void leerTarjetaParaPago();
void procesarIngresoPinPago(char tecla);
void procesarPago();
void mostrarUltimasTransacciones();
void consultarSaldoUsuario();
void leerTarjetaParaConsulta();
void consultarSaldoEnServidor(String uid);
void iniciarRegistroUsuario();
void procesarIngresoCiRegistro(char tecla);
void esperarTarjetaParaRegistro();
void leerTarjetaParaRegistro();
void procesarIngresoPinRegistro(char tecla);
void registrarUsuarioEnServidor();
void cancelarOperacion();
void mostrarMensaje(String mensaje, int duracion);

// ---------- SETUP ----------
void setup() {
  Serial.begin(115200);
  delay(10);

  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.print("Iniciando Sistema");
  lcd.setCursor(0,1);
  lcd.print("ESP32 RFID...");
  delay(900);

  // RFID init
  SPI.begin();
  rfid.PCD_Init();
  delay(100);
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print("Version RFID: 0x"); Serial.println(version, HEX);
  if (version == 0x00 || version == 0xFF) {
    lcd.clear(); lcd.print("ERROR: RFID");
    lcd.setCursor(0,1); lcd.print("Verificar conex.");
    while(true){ delay(1000); }
  }
  rfid.PCD_SetAntennaGain(rfid.RxGain_38dB);

  conectarWiFi();
  cargarDatosIniciales();

  lcd.clear();
  lcd.print("Sistema Listo!");
  lcd.setCursor(0,1); lcd.print("Menu Principal");
  delay(1200);
  mostrarMenuPrincipal();
}

// ---------- LOOP ----------
void loop() {
  char tecla = keypad.getKey();

  switch(estadoActual) {
    case MENU_PRINCIPAL:
      if (tecla) procesarMenuPrincipal(tecla);
      break;

    case INGRESO_MONTO:
      if (tecla) procesarIngresoMonto(tecla);
      break;

    case ESPERANDO_TARJETA_PAGO:
      if (tecla == '*') cancelarOperacion();
      else leerTarjetaParaPago();
      break;

    case INGRESO_PIN_PAGO:
      if (tecla) procesarIngresoPinPago(tecla);
      break;

    case INGRESO_CI_REGISTRO:
      if (tecla) procesarIngresoCiRegistro(tecla);
      break;

    case ESPERANDO_TARJETA_REGISTRO:
      if (tecla == '*') cancelarOperacion();
      else leerTarjetaParaRegistro();
      break;

    case INGRESO_PIN_REGISTRO:
      if (tecla) procesarIngresoPinRegistro(tecla);
      break;

    case CONSULTANDO_SALDO:
      if (tecla == '*') mostrarMenuPrincipal();
      else leerTarjetaParaConsulta();
      break;
  }

  delay(40);
}

// ---------- FUNCIONES BÁSICAS ----------

// Conectar WiFi
void conectarWiFi() {
  lcd.clear(); lcd.print("Conectando WiFi...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 30) {
    delay(500);
    Serial.print(".");
    intentos++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    wifiConectado = true;
    Serial.println("\nWiFi CONECTADO!");
    Serial.print("IP: "); Serial.println(WiFi.localIP());
    lcd.clear(); lcd.print("WiFi: CONECTADO");
    lcd.setCursor(0,1);
    lcd.print("IP:");
    lcd.setCursor(4,1);
    lcd.print(WiFi.localIP().toString());
    delay(1200);
  } else {
    wifiConectado = false;
    Serial.println("\nERROR: No se pudo conectar WiFi");
    lcd.clear(); lcd.print("ERROR: WiFi");
    lcd.setCursor(0,1); lcd.print("Modo sin conexion");
    delay(1200);
  }
}

// Cargar datos iniciales del tarjetero
void cargarDatosIniciales() {
  if (!wifiConectado) {
    Serial.println("Sin WiFi - No se cargan datos");
    return;
  }
  HTTPClient http;
  String url = String(API_HOST) + "/tarjetero/" + String(ID_TARJETERO);
  http.begin(url);
  int httpCode = http.GET();
  if (httpCode == 200) {
    String res = http.getString();
    DynamicJsonDocument doc(4096);
    DeserializationError err = deserializeJson(doc, res);
    if (!err) {
      saldoCaja = doc["tarjetero"]["saldo"] | 0.0;
      Serial.print("Saldo caja: "); Serial.println(saldoCaja);
      lcd.clear(); lcd.print("Datos cargados OK");
      lcd.setCursor(0,1); lcd.print("Caja:$"); lcd.print(String(saldoCaja,2));
      delay(900);
    }
  } else {
    Serial.print("Error GET tarjetero: "); Serial.println(httpCode);
  }
  http.end();
}

// Mostrar menu principal
void mostrarMenuPrincipal() {
  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print("A-Transferir  B-Ultimas");
  lcd.setCursor(0,1);
  lcd.print("C-Mi Saldo   D-Registrar");
  estadoActual = MENU_PRINCIPAL;
}

// Procesar selección menú
void procesarMenuPrincipal(char tecla) {
  switch(tecla) {
    case 'A': iniciarTransferencia(); break;
    case 'B': mostrarUltimasTransacciones(); break;
    case 'C': consultarSaldoUsuario(); break;
    case 'D': iniciarRegistroUsuario(); break;
    default: break;
  }
}

// ---------- TRANSFERENCIA (OPCION A) ----------

void iniciarTransferencia() {
  montoTemp = 0;
  estadoActual = INGRESO_MONTO;
  lcd.clear();
  lcd.print("TRANSFERENCIA");
  lcd.setCursor(0,1); lcd.print("Ingrese monto: $0.00");
  lcd.setCursor(0,3); lcd.print("#=Cont  *=Cancelar");
}

// Ingreso monto por keypad (digitos, C=backspace, #=confirm)
void procesarIngresoMonto(char tecla) {
  static String montoStr = "";
  if (tecla == '#') {
    if (montoStr.toFloat() > 0.0) {
      montoTemp = montoStr.toFloat() / 1.0; //para centavos
      if (montoStr.length() == 0) {
        mostrarMensaje("Monto invalido", 1200);
        iniciarTransferencia();
        return;
      }
      if (montoStr.length() == 1) montoTemp = montoStr.toFloat() / 10.0;
      else if (montoStr.length() == 2) montoTemp = montoStr.toFloat() / 100.0;
      else {
        String pEntera = montoStr.substring(0, montoStr.length()-2);
        String pDec = montoStr.substring(montoStr.length()-2);
        montoTemp = pEntera.toFloat() + (pDec.toFloat() / 100.0);
      }
      esperarTarjetaParaPago();
      montoStr = "";
    } else {
      mostrarMensaje("Monto invalido", 1200);
      iniciarTransferencia();
    }
  } else if (tecla == '*') {
    mostrarMenuPrincipal();
  } else if (tecla >= '0' && tecla <= '9') {
    if (montoStr.length() < 9) {
      montoStr += tecla;
      actualizarDisplayMonto(montoStr);
    }
  } else if (tecla == 'C') {
    if (montoStr.length() > 0) {
      montoStr.remove(montoStr.length()-1);
      actualizarDisplayMonto(montoStr);
    }
  }
}

// Actualizar display de monto desde string de digitos (ultimos 2 son decimales)
void actualizarDisplayMonto(String montoStr) {
  lcd.setCursor(0,1);
  lcd.print("Ingrese monto: $");
  if (montoStr.length() == 0) {
    lcd.print("0.00   ");
  } else if (montoStr.length() == 1) {
    lcd.print("0.0" + montoStr + "   ");
  } else if (montoStr.length() == 2) {
    lcd.print("0." + montoStr + "   ");
  } else {
    String parteEntera = montoStr.substring(0, montoStr.length()-2);
    String parteDecimal = montoStr.substring(montoStr.length()-2);
    lcd.print(parteEntera + "." + parteDecimal + "   ");
  }
}

// Mostrar mensaje esperando tarjeta para pago
void esperarTarjetaParaPago() {
  estadoActual = ESPERANDO_TARJETA_PAGO;
  uidTemp = "";
  pinTemp = "";
  lcd.clear();
  lcd.print("TRANSFERENCIA");
  lcd.setCursor(0,1);
  lcd.print("Monto: $" + String(montoTemp, 2));
  lcd.setCursor(0,2);
  lcd.print("Acercar tarjeta...");
  lcd.setCursor(0,3);
  lcd.print("* = Cancelar");
}

// Leer tarjeta para pago 
void leerTarjetaParaPago() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  uidTemp = uid;

  lcd.clear();
  lcd.print("Tarjeta detectada");
  lcd.setCursor(0,1);
  lcd.print("UID: " + uid.substring(0,8));
  lcd.setCursor(0,2);
  lcd.print("Ingrese PIN");
  lcd.setCursor(0,3);
  lcd.print("#=OK *=Cancelar");
  pinTemp = "";
  estadoActual = INGRESO_PIN_PAGO;

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

// Procesar PIN pago
void procesarIngresoPinPago(char tecla) {
  if (tecla == '#') {
    if (pinTemp.length() == 4) {
      procesarPago();
    } else {
      mostrarMensaje("PIN debe ser 4 digitos", 1200);
    }
  } else if (tecla == '*') {
    mostrarMenuPrincipal();
  } else if (tecla >= '0' && tecla <= '9') {
    if (pinTemp.length() < 4) {
      pinTemp += tecla;
      lcd.setCursor(10,1);
      for (int i=0;i<4;i++) lcd.print(" ");
      lcd.setCursor(10,1);
      for (int i=0;i<pinTemp.length();i++) lcd.print("*");
    }
  } else if (tecla == 'C') {
    if (pinTemp.length() > 0) {
      pinTemp.remove(pinTemp.length()-1);
      lcd.setCursor(10,1);
      for (int i=0;i<4;i++) lcd.print(" ");
      lcd.setCursor(10,1);
      for (int i=0;i<pinTemp.length();i++) lcd.print("*");
    }
  }
}

void procesarPago() {
  if (!wifiConectado) {
    mostrarMensaje("Sin conexion WiFi", 1500);
    mostrarMenuPrincipal();
    return;
  }

  lcd.clear();
  lcd.print("PROCESANDO PAGO...");
  HTTPClient http;
  String url = String(API_HOST) + "/transaccion";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  DynamicJsonDocument doc(512);
  doc["id_tarjetero"] = ID_TARJETERO;
  doc["uid_tarjeta"] = uidTemp;
  doc["pin"] = pinTemp;
  doc["monto"] = montoTemp;

  String out;
  serializeJson(doc, out);
  int httpCode = http.POST(out);

  if (httpCode == 200) {
    String res = http.getString();
    DynamicJsonDocument resDoc(512);
    DeserializationError err = deserializeJson(resDoc, res);
    if (!err) {
      String estado = resDoc["estado"] | "";
      if (estado == "aprobado") {
        float nuevoSaldo = resDoc["nuevo_saldo_usuario"] | 0.0;
        String nombre = resDoc["nombre_usuario"] | "";
        lcd.clear();
        lcd.print("PAGO APROBADO!");
        lcd.setCursor(0,1);
        lcd.print("Cliente: " + nombre.substring(0, min(16, (int)nombre.length())));
        lcd.setCursor(0,2);
        lcd.print("Monto: $" + String(montoTemp,2));
        lcd.setCursor(0,3);
        lcd.print("Saldo: $" + String(nuevoSaldo,2));
        // actualizar saldo caja
        saldoCaja += montoTemp;
      } else {
        String detalle = resDoc["mensaje"] | resDoc["detail"] | "Rechazado";
        mostrarMensaje("Rechazado: " + detalle, 2500);
      }
    } else {
      mostrarMensaje("Respuesta JSON invalida", 1800);
    }
  } else if (httpCode == 400) {
    // Error 400: puede ser saldo insuficiente u otro error
    String resp = http.getString();
    DynamicJsonDocument errDoc(512);
    DeserializationError err = deserializeJson(errDoc, resp);
    if (!err) {
      String error = errDoc["error"] | "Error";
      
      // SALDO INSUFICIENTE - Mensaje simple
      if (error == "Saldo insuficiente") {
        mostrarMensaje("SALDO INSUFICIENTE", 2500);
      } else {
        // Otros errores 400
        String detalle = errDoc["detail"] | error;
        mostrarMensaje(detalle.substring(0, min(20, (int)detalle.length())), 2000);
      }
    } else {
      mostrarMensaje("Error: " + String(httpCode), 1800);
    }
  } else if (httpCode == 401) {
    mostrarMensaje("PIN INCORRECTO", 2000);
  } else if (httpCode == 404) {
    mostrarMensaje("TARJETA NO REGISTRADA", 2000);
  } else {
    String resp = http.getString();
    Serial.print("HTTP error transaccion: "); Serial.println(httpCode);
    Serial.println(resp);
    mostrarMensaje("ERROR SERVIDOR", 1500);
  }

  http.end();
  delay(300);
  mostrarMenuPrincipal();
}

// ---------- ULTIMAS TRANSACCIONES (OPCION B) ----------
void mostrarUltimasTransacciones() {
  if (!wifiConectado) {
    mostrarMensaje("Sin conexion", 1500);
    return;
  }
  lcd.clear();
  lcd.print("Cargando...");
  HTTPClient http;
  String url = String(API_HOST) + "/tarjetero/" + String(ID_TARJETERO);
  http.begin(url);
  int httpCode = http.GET();
  if (httpCode == 200) {
    String res = http.getString();
    DynamicJsonDocument doc(4096);
    DeserializationError err = deserializeJson(doc, res);
    if (!err) {
      JsonArray trans = doc["ultimas_transacciones"].as<JsonArray>();
      lcd.clear(); lcd.print("ULTIMAS TRANSACC:");
      int linea = 1;
      for (JsonObject t : trans) {
        if (linea >= 4) break;
        float monto = t["monto"] | 0.0;
        String usuario = t["usuario"] | "";
        lcd.setCursor(0,linea);
        String display = "$" + String(monto,2) + " " + usuario.substring(0, min(8, (int)usuario.length()));
        lcd.print(display);
        linea++;
      }
      lcd.setCursor(0,3); lcd.print("* Volver");
      // esperar tecla * o timeout 20s
      unsigned long inicio = millis();
      while (millis() - inicio < 20000) {
        char k = keypad.getKey();
        if (k == '*') break;
        delay(80);
      }
    } else {
      mostrarMensaje("JSON invalido", 1200);
    }
  } else {
    mostrarMensaje("Error cargando", 1400);
  }
  http.end();
  mostrarMenuPrincipal();
}

// ---------- CONSULTAR SALDO (OPCION C) ----------
void consultarSaldoUsuario() {
  estadoActual = CONSULTANDO_SALDO;
  lcd.clear();
  lcd.print("CONSULTAR SALDO");
  lcd.setCursor(0,1);
  lcd.print("Acercar su tarjeta...");
  lcd.setCursor(0,3);
  lcd.print("* = Cancelar");
}

// Leer tarjeta en modo consulta (muestra saldo)
void leerTarjetaParaConsulta() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  uidTemp = uid;
  lcd.clear();
  lcd.print("Tarjeta detectada");
  lcd.setCursor(0,1);
  lcd.print("Consultando...");
  consultarSaldoEnServidor(uid);

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

// Llamada a /consultar_saldo
void consultarSaldoEnServidor(String uid) {
  if (!wifiConectado) {
    mostrarMensaje("Sin conexion", 1200);
    mostrarMenuPrincipal();
    return;
  }
  HTTPClient http;
  String url = String(API_HOST) + "/consultar_saldo";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  DynamicJsonDocument doc(256);
  doc["uid_tarjeta"] = uid;
  String out; serializeJson(doc, out);
  int httpCode = http.POST(out);
  if (httpCode == 200) {
    String res = http.getString();
    DynamicJsonDocument resDoc(256);
    DeserializationError err = deserializeJson(resDoc, res);
    if (!err) {
      float s = resDoc["saldo"] | 0.0;
      String nombre = resDoc["nombre"] | "";
      lcd.clear();
      lcd.print("SALDO ACTUAL");
      lcd.setCursor(0,1);
      lcd.print("Usuario: " + nombre.substring(0, min(11, (int)nombre.length())));
      lcd.setCursor(0,2);
      lcd.print("Saldo: $" + String(s, 2));
      lcd.setCursor(0,3);
      lcd.print("* Volver");
    } else {
      mostrarMensaje("JSON invalido", 1200);
    }
  } else {
    mostrarMensaje("Error consulta", 1300);
  }
  http.end();
  estadoActual = CONSULTANDO_SALDO;
}

// ---------- REGISTRO (OPCION D) ----------

void iniciarRegistroUsuario() {
  estadoActual = INGRESO_CI_REGISTRO;
  ciTemp = "";
  lcd.clear();
  lcd.print("REGISTRO USUARIO");
  lcd.setCursor(0,1);
  lcd.print("Ingrese CI (Carnet):");
  lcd.setCursor(0,2);
  lcd.print("CI: ");
  lcd.setCursor(0,3);
  lcd.print("#=Cont  *=Cancelar");
}

// Ingreso CI por keypad
void procesarIngresoCiRegistro(char tecla) {
  if (tecla == '#') {
    if (ciTemp.length() > 0) {
      // llamar backend para buscar usuario por CI
      if (!wifiConectado) {
        mostrarMensaje("Sin WiFi", 1200);
        mostrarMenuPrincipal();
        return;
      }
      // POST /buscar_usuario_por_ci -> {"ci": "<ci>"}
      HTTPClient http;
      String url = String(API_HOST) + "/buscar_usuario_por_ci";
      http.begin(url);
      http.addHeader("Content-Type", "application/json");
      DynamicJsonDocument doc(256);
      doc["ci"] = ciTemp;
      String out; serializeJson(doc, out);
      int httpCode = http.POST(out);
      if (httpCode == 200) {
        String res = http.getString();
        DynamicJsonDocument resDoc(512);
        DeserializationError err = deserializeJson(resDoc, res);
        if (!err) {
          int id_usuario = resDoc["id"] | 0;
          String nombre = resDoc["nombre"] | "";
          nombreUsuario = nombre;
          // Guardamos id_usuario en pinTemp? No: mejor usar variable global temporal. Usaremos ciTemp + backend accepts id_usuario.
          // Para registrar necesitamos id_usuario: lo pedimos y lo guardamos en uidTemp? No. Creamos una variable local static via global string
          // Implementación simple: almacenamos id_usuario como texto en uidTemp (no confundir con UID real). Pero to keep names clear, create new temp: pinTemp used for pin; create idUsuarioTemp
          // We'll create idUsuarioTemp here:
          // (define idUsuarioTemp as String at top) -> but we didn't. So use nombreUsuario to show and store id in uidTemp with special prefix "ID:".
          uidTemp = "ID:" + String(id_usuario);
          lcd.clear();
          lcd.print("Usuario encontrado");
          lcd.setCursor(0,1);
          lcd.print(nombre.substring(0,16));
          lcd.setCursor(0,2);
          lcd.print("Ingrese PIN 4 digitos");
          lcd.setCursor(0,3);
          lcd.print("#=OK  *=Cancelar");
          pinTemp = "";
          estadoActual = INGRESO_PIN_REGISTRO;
        } else {
          mostrarMensaje("JSON invalido", 1200);
          mostrarMenuPrincipal();
        }
      } else if (httpCode == 404) {
        mostrarMensaje("Usuario no encontrado", 1600);
        mostrarMenuPrincipal();
      } else {
        mostrarMensaje("Error servidor", 1400);
        mostrarMenuPrincipal();
      }
      http.end();
    } else {
      mostrarMensaje("CI invalida", 1200);
    }
  } else if (tecla == '*') {
    mostrarMenuPrincipal();
  } else if (tecla >= '0' && tecla <= '9') {
    if (ciTemp.length() < 20) {
      ciTemp += tecla;
      lcd.setCursor(4,2);
      lcd.print(ciTemp + "   ");
    }
  } else if (tecla == 'C') {
    if (ciTemp.length() > 0) {
      ciTemp.remove(ciTemp.length()-1);
      lcd.setCursor(4,2);
      lcd.print(ciTemp + "   ");
    }
  }
}

// Iniciar espera de tarjeta para registro (llamado después de ingresar PIN)
void esperarTarjetaParaRegistro() {
  estadoActual = ESPERANDO_TARJETA_REGISTRO;
  lcd.clear();
  lcd.print("REGISTRO USUARIO");
  lcd.setCursor(0,1);
  lcd.print("ID/CI: " + ciTemp.substring(0, min(10, (int)ciTemp.length())));
  lcd.setCursor(0,2);
  lcd.print("Acercar tarjeta...");
  lcd.setCursor(0,3);
  lcd.print("* = Cancelar");
}

// Leer tarjeta para registro
void leerTarjetaParaRegistro() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  uidTemp = uid;

  lcd.clear();
  lcd.print("Tarjeta detectada");
  lcd.setCursor(0,1);
  lcd.print("UID: " + uid.substring(0,8));
  lcd.setCursor(0,2);
  lcd.print("Registrando...");
  // Llamar registrar_usuario
  registrarUsuarioEnServidor();

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

// Procesar PIN registro (ingresado antes de acercar la tarjeta)
void procesarIngresoPinRegistro(char tecla) {
  if (tecla == '#') {
    if (pinTemp.length() == 4) {
      // pasamos a esperar tarjeta
      esperarTarjetaParaRegistro();
    } else {
      mostrarMensaje("PIN debe ser 4 digitos", 1200);
    }
  } else if (tecla == '*') {
    mostrarMenuPrincipal();
  } else if (tecla >= '0' && tecla <= '9') {
    if (pinTemp.length() < 4) {
      pinTemp += tecla;
      lcd.setCursor(12,2);
      for (int i=0;i<4;i++) lcd.print(" ");
      lcd.setCursor(12,2);
      for (int i=0;i<pinTemp.length();i++) lcd.print("*");
    }
  } else if (tecla == 'C') {
    if (pinTemp.length() > 0) {
      pinTemp.remove(pinTemp.length()-1);
      lcd.setCursor(12,2);
      for (int i=0;i<4;i++) lcd.print(" ");
      lcd.setCursor(12,2);
      for (int i=0;i<pinTemp.length();i++) lcd.print("*");
    }
  }
}

// Registrar usuario en backend (/registrar_tarjeta)
void registrarUsuarioEnServidor() {
  if (!wifiConectado) {
    mostrarMensaje("Sin WiFi", 1200);
    mostrarMenuPrincipal();
    return;
  }
  // uidTemp tiene UID leído; uidTemp in format "..." ; uid_usuario está en uidTemp temporal con prefijo "ID:<num>" guardado anteriormente - recordar: lo guardamos en uidTemp en momento de buscar por CI -> overwritten now. To avoid confusion, we used uidTemp for two different things. To fix, we extract id_usuario from previous uidTemp stored with prefix "ID:" earlier.
  // We'll retrieve id_usuario desde la variable temporal que guardamos: it was stored previously as uidTemp = "ID:<id>" but then overwritten by real UID reading.
  // To avoid that, we should have stored id_usuario elsewhere. But since code above used uidTemp for both, we need a dedicated var. Quick fix: use ciTemp to call buscar again and get id to ensure correctness.
  // Let's call /buscar_usuario_por_ci again to obtain id_usuario.
  HTTPClient http;
  String urlBuscar = String(API_HOST) + "/buscar_usuario_por_ci";
  http.begin(urlBuscar);
  http.addHeader("Content-Type", "application/json");
  DynamicJsonDocument docB(256);
  docB["ci"] = ciTemp;
  String outB; serializeJson(docB, outB);
  int codeB = http.POST(outB);
  int id_usuario = 0;
  if (codeB == 200) {
    String resB = http.getString();
    DynamicJsonDocument docRes(512);
    deserializeJson(docRes, resB);
    id_usuario = docRes["id"] | 0;
  } else {
    http.end();
    mostrarMensaje("Error buscando ID", 1400);
    mostrarMenuPrincipal();
    return;
  }
  http.end();

  // Ahora registrar tarjeta con id_usuario
  HTTPClient http2;
  String urlReg = String(API_HOST) + "/registrar_tarjeta";
  http2.begin(urlReg);
  http2.addHeader("Content-Type", "application/json");
  DynamicJsonDocument docR(512);
  docR["uid"] = uidTemp;
  docR["pin"] = pinTemp;
  docR["id_usuario"] = id_usuario;
  String outR; serializeJson(docR, outR);
  int codeR = http2.POST(outR);
  if (codeR == 200) {
    mostrarMensaje("USUARIO REGISTRADO!", 1400);
  } else {
    String resp = http2.getString();
    Serial.print("Error registrar tarjeta: "); Serial.println(codeR);
    Serial.println(resp);
    if (codeR == 400) {
      mostrarMensaje("Tarjeta ya registrada", 1600);
    } else {
      mostrarMensaje("Error registro", 1600);
    }
  }
  http2.end();
  mostrarMenuPrincipal();
}

// ---------- UTILIDADES ----------
void cancelarOperacion() {
  mostrarMensaje("Operacion cancelada", 900);
  mostrarMenuPrincipal();
}

void mostrarMensaje(String mensaje, int duracion) {
  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print(mensaje);
  delay(duracion);
}