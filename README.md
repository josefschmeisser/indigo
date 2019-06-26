# Indigo: Empirically learned congestion control

## Training

Training is controlled by the `indigo/dagger/train.py` script.
It expects a training specification file in YAML syntax.
A sample specification file can be found in `indigo/dagger/config.yaml`.

Each such file is required to include at least one section describing how the parameter server should be set up
and another section concerning a Mininet training environment.
These sections are called "roles" and are used by the `indigo/dagger/train.py` script to set up the according environment.

Training with the provided sample config file can be initiated as follows.
On the host responsible for the parameter server:

```
$ ./train -c config.yaml ps1
```

On the host responsible for the provided Mininet environment:

```
$ ./train -c config.yaml mn1
```

## Evaluation
Note: sender has to be started first.

On the first host:

```
$ ./run_sender.py <port> [--logfile <file>]
```

On the second host:

```
$ ./run_receiver.py <sender ip> <port>
```

Make sure that `indigo/dagger/model` contains a trained model
that actually matches the tensorflow model specified in `indigo/dagger/models.py`.
