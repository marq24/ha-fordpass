## Chromium Based (Chrome / Edge) 

❗Photos are taken in Google Chrome. Edge will look differently but the same steps apply

> [!NOTE]
> It is recommended to disable any ad-blockers or extensions that might interfere with this process.  
Alternatively, you can use a private window.

### **Step 1:**
1. Open developer tools by pressing F12 on the keyboard
2. Navigate to the URL provided through HomeAssistant

![image](./../images/004.png)

### **Step 2:**
1. Enter your credentials to login to Ford with the developer tools opened
   > If developer tools are not expanded, ensure you are on the network section.  

![image](./../images/005.png)

2. Press *Sign In*
   > The spinning circle will not load, this is normal. It is at this point you will obtain your token
3. Under the network tab look for an item starting with `?code=`

![image](./../images/006.png)

4. Select the `?code=` item within the `Name` box
   > A new window will open displaying the headers

![image](./../images/007.png)

5. Select **the entire string** and copy it to the clipboard.
   > Ctrl + C
6. Proceed with installation.

***

## Firefox

> [!NOTE]
> It is recommended to disable any ad-blockers or extension that might interfere with this process. Alternatively, you can use a private window.  
Users have also reported issues using Firefox specifically.  
**If you're having trouble using Firefox it is recommended to try using a Chromium based browser.**

### **Step 1:**
1. Open developer tools by pressing F12 on the keyboard
2. Navigate to the URL provided through HomeAssistant

![image](./../images/008.png)

### **Step 2:**
1. Enter your credentials to login to Ford with the developer tools opened
2. Press *Sign In*
3. Select the item populated under Network (Item 1 in the photo below)
   > This will open a new section
4. In the `Headers` tab, scroll down until you find `Response Headers` (Item 2 in the photo below)

![image](./../images/009.png)

5. Find the `Location` section and copy the entire string.

![image](./../images/010.png)

6. Proceed with installation

