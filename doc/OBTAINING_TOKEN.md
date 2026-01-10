# Half-manual Login Flow
### This method does require some manual steps, **including the usage of the developer tools!** of your browser

> [!WARNING]
> Although this has been tested multiple times (in January–June 2025), It can't be guaranteed the method will last as Ford is consistently making changes!

> [!NOTE]
> This process requires [at least the 2025.10.2 version](https://github.com/marq24/ha-fordpass/releases/tag/2025.10.2) of this fordpass integration.


### **Step I:**
1. In Home Assistant: Enter your Fordpass username
2. You should select your region (where you have registered your FordPass account).

![image](./../images/001.png)


### **Step II:**
1. Copy the URL that has been generated and paste it in your additional/separate browser. You might like to use a private/incognito window for this.

> [!IMPORTANT]
> Ensure you have enabled the Developer tools before pressing "log in" as you will be required to capture a header once logged in!
> - [:link: Chromium based dev tools helper (Chrome / Edge)](./DEV-TOOLS.md)
>
> As _alternative_, you might also like to use Firefox (but I __can not recommend__ this, since plenty of users have issues when using Firefox):
> - [:link: Firefox dev tools helper](./DEV-TOOLS.md#firefox)


![image](./../images/002.png)

2. In your second/separate browser (where you paste the URL), the Ford Login dialog should be displayed. 

3. Enter your FordPass credentials and click `Sign In`.
> [!NOTE]
> After you have pressed the login button, the Ford Login website will just show a spinner and will not continue to load — this is the intended behavior! At this point you are able to obtain the code by using the browser tools (see next step 4).

![webrequst](./../images/003a.png)

4. Now you must use the browser tools and select the `Network tab` of the web console and view the headers section.
   
   - The last request (probably already showed in red) is the one we are interested in... Since this last request contains the code we must capture for the integration, it should start with `userauthorized/...`
   - You are looking for the contents of the "Location Header" as shown in the pic below
   - The output should look similar to the following string, starting with `fordapp://` (or `lincolnapp://`):
   - ```fordapp://userauthorized/?code=eyJraWQiOiItSm9pdi1OX1ktUWNsa***************************```
   - **Ensure you capture the entire string (copy the raw output and not the wrapped text)** and enter it into the text box of the home assistant setup dialog.
   - You then can close the Ford login browser window 

> [!NOTE]
> Again - the Ford login website will not __fully loaded__. The login page will just continue to spin. 

![webrequst](./../images/003b.png)


### **Step III:** 
- Once you've entered the copied token back in the home assistant integration setup dialog the integration should go off and get you a new set of tokens and then ask what vehicles you want to add.