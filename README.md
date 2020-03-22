# Python-IS31FL3741
A matrix-centric Python driver for the IS31FL3741 39x9 I2C scanning matrix driver.

[Datasheet](http://www.issi.com/WW/pdf/IS31FL3741.pdf)

Usage

```

matrix = IS31FL3741(address=0x6F, busnum=10, DEBUG=False)
print("powering on all pixels")
matrix.enableAllPixels()

print("powering off all pixels via PWM register")
matrix.setAllPixelsPWM([0]*39*9)

print("let's fade up from 0 to 10 on all pixels")
for value in range(10):
	matrix.setAllPixelsPWM([value]*39*9)

```

Example projects

- coming soon!
