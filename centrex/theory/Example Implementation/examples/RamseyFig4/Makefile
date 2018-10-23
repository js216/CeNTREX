CC = g++
CFLAGS = -Wall -std=c++17 -Wfatal-errors -O3
DEPS = ../bases/DecoupledBasis.h \
       ../operators/DecoupledBasisOperators.h \
       ../operators/TlF_operators.h \
       ../states/BasisState.h \
       ../states/Hash.h \
       ../states/State.h

RamseyFig4.o: RamseyFig4.cpp $(DEPS)
	$(CC) $(CFLAGS) RamseyFig4.cpp -o RamseyFig4.o
