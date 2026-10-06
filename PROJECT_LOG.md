# Project Log
In this log file I will document all the steps I've taken including what I've tried, learned, and implemented. 

## 2026-09-22

1. Brainstormed a serverless application I could create to demonstrate my knowledge of AWS services and learn how to implement
2. Worked with AI to fullproof the design, create file structure, and write an implementation guide but WITHOUT any written code, only short instructions on what needs to be done were written into the files
3. Installed all necessary software like the CDK 
4. Created IAM user with Admin access in the AWS Console. This will prevent any use of the account root user. 
5. Enabled MFA on root user and IAM user 
6. Originally wanted to generate access keys from the IAM user for the CLI, but learned about `aws login` which uses AWS Console credentials to give temporary access to the CLI
