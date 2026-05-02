^XA
^MTT
^PW800      // 10 cm width (10*203/2.54 ≈ 800 dots)
^LL1200     // 15 cm height (15*203/2.54 ≈ 1200 dots)
^MD30
^PR7

// --- "Logo": Large Cobaltax text with underline ---
^CF0,100
^FO40,40^FDCOBALTAX^FS
^FO40,160^GB700,5,5^FS

// --- Customer Info ---
^CF0,40
^FO40,200^FDTo:^FS
^FO180,200^FDJohn Doe^FS
^FO180,250^FD1234 Innovation Ave^FS
^FO180,300^FDSilicon Valley, CA 94043^FS
^FO180,350^FDUnited States^FS

// --- Product Info ---
^CF0,40
^FO40,420^FDProduct:^FS
^FO250,420^FDCobaltax UltraWidget 3000^FS
^FO40,470^FDQty:^FS
^FO180,470^FD5 units^FS
^FO40,520^FDDate:^FS
^FO180,520^FD2025-07-28^FS

// --- EAN13 Barcode ---
^BY3,2,100
^FO40,600^BEN,100,Y,N
^FD123456789012^FS
^CF0,30

// --- EAN128 Barcode (GS1-128) ---
^BY3,2,100
^FO40,800^BCN,100,Y,N,N
^FD>;>801234567890123456^FS
^CF0,30



// --- DataMatrix Code (Support) ---
^FO500,750^BXN,10,100
^FDhttps://cobaltax.com/support^FS
^CF0,30
^FO500,900^FDSupport DataMatrix^FS



^XZ