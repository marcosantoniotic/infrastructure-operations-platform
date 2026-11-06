// Disposable Windows fixture only. Never install on a domain member/DC.
using System;
using System.IO;
using System.ServiceProcess;
using System.Threading;

sealed class NativeServiceFixture : ServiceBase
{
    const string Work = @"C:\IOPWspNative";
    Timer timer;
    NativeServiceFixture(string name)
    {
        if (Environment.MachineName != "IOP-WSP-NATIVE" ||
            (name != "IOPWspNativeAlpha" && name != "IOPWspNativeBeta") ||
            !File.Exists(Path.Combine(Work, "fixture-input.private.json")))
            throw new InvalidOperationException("Not the owned disposable fixture");
        ServiceName = name; CanStop = true; AutoLog = false;
    }
    void Record(string what)
    {
        File.AppendAllText(Path.Combine(Work, ServiceName + ".lifecycle.log"),
            DateTime.UtcNow.ToString("o") + " " + what + Environment.NewLine);
    }
    protected override void OnStart(string[] args)
    {
        string mode = File.ReadAllText(Path.Combine(Work, ServiceName + ".mode")).Trim();
        Record("start " + mode);
        if (mode == "pending") { RequestAdditionalTime(45000); Thread.Sleep(20000); }
        else if (mode == "start-fail") throw new InvalidOperationException("Owned synthetic start failure");
        else if (mode != "clean" && mode != "crash" && mode != "service-error")
            throw new InvalidOperationException("Unknown owned fixture mode");
        if (mode == "crash" || mode == "service-error")
            timer = new Timer(delegate(object unused) {
                Record(mode);
                if (mode == "crash") Environment.Exit(17);
                else { ExitCode = 5; Stop(); }
            }, null, 8000, Timeout.Infinite);
    }
    protected override void OnStop() { if (timer != null) timer.Dispose(); Record("stop code=" + ExitCode); }
    static void Main(string[] args)
    {
        if (args.Length != 1) throw new ArgumentException("One owned service name required");
        ServiceBase.Run(new NativeServiceFixture(args[0]));
    }
}
