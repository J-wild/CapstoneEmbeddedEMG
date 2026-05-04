
#include <SPI.h>
#include <ADS1298.h>
#include <zephyr/kernel.h>
#include <Arduino_RouterBridge.h>

/* ADS1298 pins */
const int PSU_ANA = 4;
const int PSU_DIG = 3;
const int PWDN    = 7;
const int RST     = 6;
const int START   = 8;
const int DRDY    = 9;
const int CS      = 10;
const int CLKSEL  = 5;

const int SPI_FREQ = 1000000;


// DOUBLE BUFFER 
#define BATCH_SIZE   20
#define SAMPLE_BYTES 27                        // 9 × 3 bytes
#define BUF_SIZE     (SAMPLE_BYTES * BATCH_SIZE)

static uint8_t bufA[BUF_SIZE];
static uint8_t bufB[BUF_SIZE];

static uint8_t *fillBuf  = bufA;
static uint8_t *sendBuf  = bufB;
static int      fillPos   = 0;
static int      fillCount = 0;
static int      sendSize  = 0;
static int      sendSize  = 0;

// ZEPHYR SYNC PRIMITIVES 
static struct k_sem   send_sem;
static struct k_mutex swap_mutex;


#define SENDER_STACK_SIZE 2048 // creating a seperate stack means memory does not need to be realocated
#define SENDER_PRIORITY   7

void senderThread(void *a, void *b, void *c) { // a sender thread to manage the monitor.write function.
    while (true) {
        k_sem_take(&send_sem, K_FOREVER);   // block until buffer is ready
        Monitor.write(sendBuf, sendSize);   // send — runs at low priority
    }
}


static int           samples             = 0;
static unsigned long total_samples       = 0;
static unsigned long lastReport          = 0;

// CONVERSION - no longer used on the MCU but kept for referebce
float toMillivolts(long raw24bit) {
    if (raw24bit & 0x800000) {
        raw24bit |= 0xFF000000;
    }
    const float VREF    = 2.4;
    const float GAIN    = 12.0;
    const float MAX_VAL = 8388608.0;
    float volts = ((float)raw24bit * VREF) / (GAIN * MAX_VAL);
    return volts * 1000.0;
}

// SPI COMMANDS 
//these whare adapted from the ADS129x library by ferdinandkeil https://github.com/ferdinandkeil/ADS129X and implimended as direct functions 
// as the arduino app lab had no ability to use unlisted external libraries at the time of development
void SDATAC() {
    SPI.beginTransaction(SPISettings(SPI_FREQ, MSBFIRST, SPI_MODE1));
    digitalWrite(CS, LOW);
    SPI.transfer(ADS129X_CMD_SDATAC);
    delayMicroseconds(2);
    digitalWrite(CS, HIGH);
    SPI.endTransaction();
}

void RDATAC() {
    SPI.beginTransaction(SPISettings(SPI_FREQ, MSBFIRST, SPI_MODE1));
    digitalWrite(CS, LOW);
    SPI.transfer(ADS129X_CMD_RDATAC);
    delayMicroseconds(2);
    digitalWrite(CS, HIGH);
    delayMicroseconds(2);
    SPI.endTransaction();
}

void WREG(byte _address, byte _value) {
    SPI.beginTransaction(SPISettings(SPI_FREQ, MSBFIRST, SPI_MODE1));
    byte opcode1 = ADS129X_CMD_WREG | (_address & 0x1F);
    digitalWrite(CS, LOW);
    SPI.transfer(opcode1);
    SPI.transfer(0x00);
    SPI.transfer(_value);
    delayMicroseconds(2);
    digitalWrite(CS, HIGH);
    SPI.endTransaction();
}

void configChannel(byte _channel, boolean _powerDown, byte _gain, byte _mux) {
    byte value = ((_powerDown & 1) << 7) | ((_gain & 7) << 4) | (_mux & 7);
    WREG(ADS129X_REG_CH1SET + (_channel - 1), value);
}

byte getDeviceId() {
    SPI.beginTransaction(SPISettings(SPI_FREQ, MSBFIRST, SPI_MODE1));
    digitalWrite(CS, LOW);
    SPI.transfer(ADS129X_CMD_RREG);
    SPI.transfer(0x00);
    byte data = SPI.transfer(0x00);
    delayMicroseconds(2);
    digitalWrite(CS, HIGH);
    SPI.endTransaction();
    return data;
}

boolean getData(long *buffer) {
    if (digitalRead(DRDY) == LOW) {
        SPI.beginTransaction(SPISettings(SPI_FREQ, MSBFIRST, SPI_MODE1));
        digitalWrite(CS, LOW);
        for (int i = 0; i < 9; i++) {
            long dataPacket = 0;
            for (int j = 0; j < 3; j++) {
                byte dataByte = SPI.transfer(0x00);
                dataPacket = (dataPacket << 8) | dataByte;
            }
            buffer[i] = dataPacket;
        }
        digitalWrite(CS, HIGH);
        SPI.endTransaction();
        return true;
    }
    return false;
}

void STARTCMD() {
    SPI.beginTransaction(SPISettings(SPI_FREQ, MSBFIRST, SPI_MODE1));
    digitalWrite(CS, LOW);
    SPI.transfer(0x08);
    delayMicroseconds(2);
    digitalWrite(CS, HIGH);
    SPI.endTransaction();
}

void RESETCMD() {
    SPI.beginTransaction(SPISettings(SPI_FREQ, MSBFIRST, SPI_MODE1));     
    digitalWrite(CS, LOW);
    SPI.transfer(ADS129X_CMD_RESET);
    delayMicroseconds(2);
    digitalWrite(CS, HIGH);
    delay(10); //must wait 18 tCLK cycles to execute this command (Datasheet, pg. 38)
    SPI.endTransaction();    
}

// HARDWARE INIT 
void setPinIO() {
    pinMode(DRDY,    INPUT_PULLUP);
    pinMode(PSU_DIG, OUTPUT);
    pinMode(PSU_ANA, OUTPUT);
    pinMode(RST,     OUTPUT);
    pinMode(PWDN,    OUTPUT);
    pinMode(START,   OUTPUT);
    pinMode(CLKSEL,  OUTPUT);
    pinMode(CS,      OUTPUT);
}

void StartProc() {
    digitalWrite(PWDN,  LOW);
    digitalWrite(RST,   LOW);
    digitalWrite(START, LOW);
    digitalWrite(CS,    LOW);
    digitalWrite(CLKSEL,LOW);

    digitalWrite(PSU_DIG, HIGH);  // Power up sequencing
    digitalWrite(PSU_ANA, HIGH);
    delay(100);


    digitalWrite(CS,     HIGH);
    digitalWrite(CLKSEL, HIGH);
    delay(100);

    //digitalWrite(PWDN, HIGH);
    //delay(10);
    RESETCMD();

    
   
}

void ConfigADS() {
    delay(100);

    WREG(ADS129X_REG_CONFIG1, (0 << ADS129X_BIT_HR) | ADS129X_SAMPLERATE_1024);
    delay(100);

    // Read back to verify
    SPI.beginTransaction(SPISettings(SPI_FREQ, MSBFIRST, SPI_MODE1));
    digitalWrite(CS, LOW);
    SPI.transfer(ADS129X_CMD_RREG | 0x01);
    SPI.transfer(0x00);
    byte r1 = SPI.transfer(0x00);
    digitalWrite(CS, HIGH);
    SPI.endTransaction();

    Monitor.print("CONFIG1 = 0b");
    Monitor.println(r1, BIN);

    WREG(ADS129X_REG_CONFIG3, (1 << ADS129X_BIT_PD_REFBUF) | (1 << 6));

    //WREG(ADS129X_REG_CONFIG2, (1<<ADS129X_BIT_INT_TEST) | ADS129X_TEST_FREQ_1HZ);
    delay(50);
    configChannel(1, false, ADS129X_GAIN_12X, ADS129X_MUX_NORMAL);

    for (int i = 2; i <= 8; i++) {
        delay(50);
        configChannel(i, false, ADS129X_GAIN_12X, ADS129X_MUX_SHORT);
    }
}

//BATCH / SEND 
void appendSampleToBatch(long *buffer) {
    uint8_t *p = fillBuf + fillPos;
    for (int i = 0; i < 9; i++) {
        long v = buffer[i] & 0xFFFFFF;
        *p++ = (v >> 16) & 0xFF;
        *p++ = (v >>  8) & 0xFF;
        *p++ =  v        & 0xFF;
    }
    fillPos += SAMPLE_BYTES;
    fillCount++;

    if (fillCount >= BATCH_SIZE) {
        k_mutex_lock(&swap_mutex, K_FOREVER);

        // Swap buffers — acquisition immediately continues into the other buffer
        sendBuf  = fillBuf;
        sendSize = fillPos;
        fillBuf  = (fillBuf == bufA) ? bufB : bufA;
        fillPos   = 0;
        fillCount = 0;

        k_mutex_unlock(&swap_mutex);

        // Wake sender thread 
        k_sem_give(&send_sem);
    }
}

// ── SETUP ─────────────────────────────────────────────────────────────────────
void setup() {
    if (!Monitor.begin()) { while (true) {} }
    delay(1000);
    Monitor.println("Application Started: Setting Pin Configurations");

    SPI.begin();
    delay(100);

    // ADS1298 hardware init
    setPinIO();
    StartProc();
    Monitor.println("Done with start Procedure");

    SDATAC();  // put ads into listening config
    delay(100);

    byte id = getDeviceId(); // connect to the ADS and return its ID
    Monitor.print("Device ID: 0x");
    Monitor.println(id, HEX);

    if (id != 0x92) {
       Monitor.println("ERROR: ADS1298 not found - check wiring, halting");
        while (1);
    }

    delay(50);   
    ConfigADS();

    delay(50);
    STARTCMD();

    delay(100); 
    RDATAC(); // put ads into read data config

    Monitor.println("Conversions started - streaming data");
    delay(100);

    Monitor.print("READY batch=");
    Monitor.println(BATCH_SIZE);

    lastReport = millis();
}

// LOOP
void loop() {
    long buffer[9];

    // debug info output the current sample rate every second
    if (digitalRead(DRDY) == HIGH) {

        if (millis() - lastReport >= 1000) {
            
            Monitor.print("SPS: ");
            Monitor.println(" ");
            Monitor.println(samples);
            Monitor.print("Total: ");
            Monitor.println(total_samples);
            samples    = 0;
            lastReport = millis();
        }
        
        return;
        
    }

    // when data is avalable from the serial read command append it to the buffer and update the sample count
    if (getData(buffer)) {
        appendSampleToBatch(buffer);
        samples++;
        total_samples++;
    }
}