# Indigo: Empirically learned congestion control

## Training

## Evaluation

Note: sender has to be started first.

On the first host:

```
$ run_sender.py <port> [--logfile <file>]
```

On the second host:

```
$ run_receiver.py <sender ip> <port>
```

Make sure that `indigo/dagger/model` contains a trained model
that actually matches the tensorflow model specified in `indigo/dagger/models.py`.
