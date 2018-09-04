CC = g++
CFLAGS = -Wall -std=c++17
DEPS = ../bases/DecoupledBasis.h \
       ../operators/DecoupledBasisOperators.h \
       ../states/BasisState.h \
       ../states/Hash.h \
       ../states/State.h

all: state_tests.o bases_tests.o

state_tests.o: state_tests.cpp $(DEPS)
	$(CC) $(CFLAGS) state_tests.cpp -o state_tests.o
	./state_tests.o
	rm state_tests.o

bases_tests.o: bases_tests.cpp $(DEPS)
	$(CC) $(CFLAGS) bases_tests.cpp -o bases_tests.o
	./bases_tests.o
	rm bases_tests.o
